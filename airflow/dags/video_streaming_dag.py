from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.utils.dates import days_ago
from datetime import timedelta

dag = DAG(
    'video_streaming_pipeline',
    schedule_interval=None,
    catchup=False
)

# Task 1: Kafka Producer (Ingestion)
# Note: Spark processor and Kafka consumer run as standalone Docker services.
# They continuously process frames in the background.
# This DAG only triggers the producer via backend API.
def start_kafka_producer(**context):
    """Trigger video streaming by calling backend API"""
    import requests
    import json
    
    video_id = context['dag_run'].conf['video_id']
    video_path = context['dag_run'].conf['video_path']
    fps = context['dag_run'].conf.get('fps', 30)
    duration = context['dag_run'].conf.get('duration', 0)
    
    # Call backend API to start producer
    backend_url = 'http://video_streaming_backend:8686/api/producer/stream'
    payload = {
        'video_id': video_id,
        'video_path': video_path,
        'fps': fps,
        'duration': duration
    }
    
    print(f"Calling backend API: {backend_url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    response = requests.post(backend_url, json=payload, timeout=300)
    
    if response.status_code == 200:
        result = response.json()
        print(f"✓ Producer started successfully: {result}")
        return result
    else:
        error_msg = f"Producer API failed with status {response.status_code}: {response.text}"
        print(f"✗ {error_msg}")
        raise Exception(error_msg)

task_producer = PythonOperator(
    task_id='kafka_producer',
    python_callable=start_kafka_producer,
    dag=dag
)

# Task 2: Cleanup and Analytics Summary (Phase 3)
def cleanup_and_summarize(**context):
    """
    Clean up Redis cache and create analytics summary
    Called after video processing completes
    """
    import sys
    sys.path.insert(0, '/opt/airflow/backend')
    
    from models.video import get_db, VideoAnalyticsSummary, VideoAnalyticsSnapshot, SpeedingVehicle
    from sqlalchemy import func, desc
    from datetime import datetime
    
    video_id = context['dag_run'].conf['video_id']
    print(f"Running cleanup and analytics summary for video_id: {video_id}")
    
    db = get_db()
    try:
        # Get the most recent session for this video
        latest_snapshot = db.query(VideoAnalyticsSnapshot).filter(
            VideoAnalyticsSnapshot.video_id == video_id
        ).order_by(desc(VideoAnalyticsSnapshot.created_at)).first()
        
        if not latest_snapshot:
            print("No snapshots found, skipping summary creation")
            return {'status': 'skipped', 'reason': 'no_data'}
        
        session_start = latest_snapshot.session_start
        
        # Calculate aggregated statistics from snapshots
        max_concurrent = db.query(func.max(VideoAnalyticsSnapshot.current_in_roi)).filter(
            VideoAnalyticsSnapshot.video_id == video_id,
            VideoAnalyticsSnapshot.session_start == session_start
        ).scalar() or 0
        
        total_frames = db.query(func.count(VideoAnalyticsSnapshot.id)).filter(
            VideoAnalyticsSnapshot.video_id == video_id,
            VideoAnalyticsSnapshot.session_start == session_start
        ).scalar() or 0
        
        # Get final vehicle count from last snapshot
        final_vehicle_count = latest_snapshot.total_vehicles
        
        # Get speeding vehicle statistics
        speeding_vehicles = db.query(SpeedingVehicle).filter(
            SpeedingVehicle.video_id == video_id,
            SpeedingVehicle.session_start == session_start
        ).all()
        
        total_speeding_violations = len(set(v.track_id for v in speeding_vehicles))  # Unique vehicles
        
        if speeding_vehicles:
            speeds = [v.speed for v in speeding_vehicles]
            avg_speed = sum(speeds) / len(speeds)
            max_speed = max(speeds)
            
            # Speed distribution
            speed_distribution = {
                '60-70': len([s for s in speeds if 60 <= s < 70]),
                '70-80': len([s for s in speeds if 70 <= s < 80]),
                '80-90': len([s for s in speeds if 80 <= s < 90]),
                '90+': len([s for s in speeds if s >= 90])
            }
            
            # Vehicle type distribution
            vehicle_types = {}
            for v in speeding_vehicles:
                class_name = v.class_name or 'unknown'
                vehicle_types[class_name] = vehicle_types.get(class_name, 0) + 1
        else:
            avg_speed = 0.0
            max_speed = 0.0
            speed_distribution = {}
            vehicle_types = {}
        
        # Calculate processing duration
        if session_start:
            session_end = datetime.utcnow()
            duration_seconds = int((session_end - session_start).total_seconds())
            avg_fps = total_frames / duration_seconds if duration_seconds > 0 else 0
        else:
            session_end = None
            duration_seconds = 0
            avg_fps = 0.0
        
        # Create or update summary
        existing_summary = db.query(VideoAnalyticsSummary).filter(
            VideoAnalyticsSummary.video_id == video_id,
            VideoAnalyticsSummary.session_start == session_start
        ).first()
        
        if existing_summary:
            print(f"Updating existing summary for session {session_start}")
            summary = existing_summary
        else:
            print(f"Creating new summary for session {session_start}")
            summary = VideoAnalyticsSummary(
                video_id=video_id,
                session_start=session_start
            )
        
        # Update summary fields
        summary.total_vehicles_detected = final_vehicle_count
        summary.total_speeding_violations = total_speeding_violations
        summary.max_concurrent_vehicles = max_concurrent
        summary.avg_processing_fps = round(avg_fps, 2)
        summary.total_frames_processed = total_frames
        summary.vehicle_type_distribution = vehicle_types
        summary.avg_speed = round(avg_speed, 2) if avg_speed > 0 else None
        summary.max_speed = round(max_speed, 2) if max_speed > 0 else None
        summary.speed_distribution = speed_distribution
        summary.session_end = session_end
        summary.processing_duration_seconds = duration_seconds
        
        if not existing_summary:
            db.add(summary)
        
        db.commit()
        
        result = {
            'status': 'success',
            'video_id': video_id,
            'session_start': session_start.isoformat() if session_start else None,
            'total_vehicles': final_vehicle_count,
            'speeding_violations': total_speeding_violations,
            'max_concurrent': max_concurrent,
            'avg_fps': round(avg_fps, 2),
            'total_frames': total_frames,
            'duration_seconds': duration_seconds
        }
        
        print(f"✓ Analytics summary created: {result}")
        return result
        
    except Exception as e:
        db.rollback()
        print(f"✗ Error creating analytics summary: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()

task_cleanup = PythonOperator(
    task_id='cleanup_and_summarize',
    python_callable=cleanup_and_summarize,
    dag=dag
)

# Task dependencies
task_producer >> task_cleanup

# Only producer task - Spark and Consumer are standalone services
# Data Flow: DAG → Backend Producer → Redis → Spark (standalone) → Consumer (standalone) → WebSocket
