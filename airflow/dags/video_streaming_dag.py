from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.sensors.python import PythonSensor
from airflow.utils.dates import days_ago
from datetime import timedelta, datetime
import time

dag = DAG(
    'video_streaming_pipeline',
    start_date=datetime(2025, 1, 1),  # Start date in the past
    schedule_interval=None,  # Manual trigger only
    catchup=False  # Don't backfill
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
        
        # Store total frames sent in XCom for the sensor to check
        if 'total_frames' in result:
            context['ti'].xcom_push(key='total_frames_sent', value=result['total_frames'])
            print(f"  Total frames to process: {result['total_frames']}")
        
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

# Task 2: Wait for video processing to complete
def wait_for_processing_complete(**context):
    """
    Check if video processing has completed by comparing frames sent vs processed
    Returns True when processing is done, False otherwise
    """
    import sys
    import os
    from datetime import datetime, timedelta
    import time
    
    # Add backend path for imports
    backend_path = '/opt/airflow/backend'
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)
    
    if 'DATABASE_URL' not in os.environ:
        os.environ['DATABASE_URL'] = 'postgresql://postgres:postgres@postgres:5432/video_streaming'
    
    from models.video import VideoAnalyticsSnapshot
    from database import get_db
    
    dag_run = context.get('dag_run')
    video_id = dag_run.conf.get('video_id') if dag_run and dag_run.conf else None
    
    if not video_id:
        print("No video_id found")
        return False
    
    # Get total frames sent by producer
    ti = context['ti']
    total_frames_sent = ti.xcom_pull(task_ids='kafka_producer', key='total_frames_sent')
    
    # Track last snapshot info across pokes
    if not hasattr(wait_for_processing_complete, 'state'):
        wait_for_processing_complete.state = {}
    
    try:
        db = get_db()
        
        # Get the most recent snapshot
        latest_snapshot = db.query(VideoAnalyticsSnapshot).filter(
            VideoAnalyticsSnapshot.video_id == video_id
        ).order_by(VideoAnalyticsSnapshot.timestamp.desc()).first()
        
        if not latest_snapshot:
            print(f"No snapshots yet for video {video_id}... waiting")
            db.close()
            return False
        
        current_time = time.time()
        last_frame = latest_snapshot.frame_number
        last_snapshot_time = latest_snapshot.timestamp
        
        # Method 1: If we know total frames, check if we've processed them all
        if total_frames_sent:
            print(f"Video {video_id}: Processed {last_frame}/{total_frames_sent} frames")
            
            # Allow a small buffer (frames might be slightly different due to processing)
            if last_frame >= total_frames_sent - 5:
                # Wait an additional 15 seconds to ensure all analytics are persisted
                state_key = f"{video_id}_completion_wait"
                if state_key not in wait_for_processing_complete.state:
                    wait_for_processing_complete.state[state_key] = current_time
                    print(f"  Reached final frame. Waiting 15s for analytics persistence...")
                    db.close()
                    return False
                elif current_time - wait_for_processing_complete.state[state_key] >= 15:
                    print(f"✓ Video {video_id} processing completed ({last_frame} frames processed)")
                    db.close()
                    return True
                else:
                    remaining = 15 - (current_time - wait_for_processing_complete.state[state_key])
                    print(f"  Waiting {int(remaining)}s more for analytics to persist...")
                    db.close()
                    return False
        
        # Method 2: If total frames unknown, detect stale snapshots (fallback)
        else:
            print(f"Video {video_id}: Frame {last_frame} (total unknown, using timeout method)")
            
            state_key = f"{video_id}_last_snapshot"
            if state_key in wait_for_processing_complete.state:
                prev_frame, prev_time = wait_for_processing_complete.state[state_key]
                
                # If no new frames for 45 seconds, assume complete
                if last_frame == prev_frame and (current_time - last_snapshot_time) > 45:
                    print(f"✓ Video {video_id} processing completed (no new frames for 45s)")
                    db.close()
                    return True
            
            wait_for_processing_complete.state[state_key] = (last_frame, last_snapshot_time)
        
        db.close()
        return False
        
    except Exception as e:
        print(f"Error checking processing status: {e}")
        import traceback
        traceback.print_exc()
        return False

wait_for_completion = PythonSensor(
    task_id='wait_for_processing',
    python_callable=wait_for_processing_complete,
    poke_interval=30,  # Check every 30 seconds
    timeout=3600,  # Timeout after 1 hour
    mode='poke',  # Use poke mode (blocking)
    dag=dag
)

# Task 3: Cleanup and Analytics Summary (Phase 3)
def cleanup_and_summarize(**context):
    """Cleanup task that runs after video processing completes"""
    import sys
    import os
    import redis
    import json
    from datetime import datetime
    from sqlalchemy import func
    
    # Add backend path to sys.path for imports
    backend_path = '/opt/airflow/backend'
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)
    
    # Set DATABASE_URL for Docker environment (postgres is the service name)
    if 'DATABASE_URL' not in os.environ:
        os.environ['DATABASE_URL'] = 'postgresql://postgres:postgres@postgres:5432/video_streaming'
    
    from models.video import VideoAnalyticsSnapshot, SpeedingVehicle, VideoAnalyticsSummary
    from database import get_db
    
    # Get video_id from DAG run configuration
    dag_run = context.get('dag_run')
    video_id = None
    
    if dag_run and dag_run.conf:
        video_id = dag_run.conf.get('video_id')
    
    if not video_id:
        print("No video_id found in DAG configuration, skipping cleanup")
        return {'status': 'skipped', 'reason': 'no_video_id'}
    
    print(f"Running cleanup and analytics summary for video_id: {video_id}")
    
    db = get_db()
    
    try:
        # Get the latest snapshot for this video
        latest_snapshot = db.query(VideoAnalyticsSnapshot).filter(
            VideoAnalyticsSnapshot.video_id == video_id
        ).order_by(VideoAnalyticsSnapshot.timestamp.desc()).first()
        
        if not latest_snapshot:
            print(f"No snapshots found for video {video_id}")
            return {'status': 'skipped', 'reason': 'no_data'}
        
        session_start = latest_snapshot.session_start
        
        # Get total frames sent from producer (via XCom)
        ti = context['ti']
        total_frames_sent = ti.xcom_pull(task_ids='kafka_producer', key='total_frames_sent')
        
        # Calculate aggregated statistics from snapshots
        max_concurrent = db.query(func.max(VideoAnalyticsSnapshot.current_in_roi)).filter(
            VideoAnalyticsSnapshot.video_id == video_id,
            VideoAnalyticsSnapshot.session_start == session_start
        ).scalar() or 0
        
        # Get actual frames processed from latest snapshot's frame_number
        total_frames_processed = latest_snapshot.frame_number if latest_snapshot else 0
        
        # Validate against producer data
        if total_frames_sent:
            print(f"  Frame validation: Producer sent {total_frames_sent}, Processed {total_frames_processed}")
            if abs(total_frames_sent - total_frames_processed) > 5:
                print(f"  ⚠️ WARNING: Frame count mismatch > 5 frames!")
        
        # Use processed count as source of truth (actual work done)
        total_frames = total_frames_processed
        
        # FIX: Get the MAXIMUM total_vehicles from all snapshots, not just the last one
        # This ensures we capture the final count even if last snapshot was taken early
        max_from_snapshots = db.query(func.max(VideoAnalyticsSnapshot.total_vehicles)).filter(
            VideoAnalyticsSnapshot.video_id == video_id,
            VideoAnalyticsSnapshot.session_start == session_start
        ).scalar() or 0
        
        # Check the latest snapshot's count for comparison
        latest_snapshot_count = latest_snapshot.total_vehicles if latest_snapshot else 0
        
        print(f"  Vehicle count from snapshots: MAX={max_from_snapshots}, Latest={latest_snapshot_count}")
        
        # Also try to get the real-time count from Redis (if still available)
        redis_count = None
        try:
            redis_client = redis.Redis(
                host=os.getenv('REDIS_HOST', 'redis'),
                port=int(os.getenv('REDIS_PORT', 6379)),
                decode_responses=True
            )
            redis_key = f"analytics:video:{video_id}"
            redis_data = redis_client.get(redis_key)
            if redis_data:
                redis_metrics = json.loads(redis_data)
                redis_count = redis_metrics.get('total_vehicles_count', 0)
                print(f"  Vehicle count from Redis: {redis_count}")
        except Exception as redis_err:
            print(f"  Could not fetch from Redis: {redis_err}")
        
        # Use the highest value from all sources
        final_vehicle_count = max(
            max_from_snapshots,
            latest_snapshot_count,
            redis_count if redis_count else 0
        )
        
        print(f"  ✓ Final vehicle count (using highest): {final_vehicle_count}")
        
        # Diagnostic: Count unique track_ids from all snapshots to verify
        # This helps identify if vehicles are being lost between snapshots
        snapshot_count = db.query(func.count(VideoAnalyticsSnapshot.id)).filter(
            VideoAnalyticsSnapshot.video_id == video_id,
            VideoAnalyticsSnapshot.session_start == session_start
        ).scalar() or 0
        print(f"  Diagnostics: {snapshot_count} snapshots saved, covering {total_frames} frames")
        
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
            
            # Speed distribution - count unique vehicles per range (use max speed per vehicle)
            # Group by track_id and get max speed for each vehicle
            vehicle_max_speeds = {}
            for v in speeding_vehicles:
                if v.track_id not in vehicle_max_speeds or v.speed > vehicle_max_speeds[v.track_id]:
                    vehicle_max_speeds[v.track_id] = v.speed
            
            # Now count unique vehicles in each speed range based on their max recorded speed
            unique_speeds = list(vehicle_max_speeds.values())
            speed_distribution = {
                'range_60_70': len([s for s in unique_speeds if 60 <= s < 70]),
                'range_70_80': len([s for s in unique_speeds if 70 <= s < 80]),
                'range_80_90': len([s for s in unique_speeds if 80 <= s < 90]),
                'range_90_plus': len([s for s in unique_speeds if s >= 90])
            }
            
            # Vehicle type distribution - also count unique vehicles
            vehicle_types = {}
            seen_track_ids = set()
            for v in speeding_vehicles:
                if v.track_id not in seen_track_ids:
                    seen_track_ids.add(v.track_id)
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
# Producer → Wait for completion → Cleanup
task_producer >> wait_for_completion >> task_cleanup

# Data Flow: 
# DAG → Producer → Redis → Spark (processes frames) → [Wait Sensor] → Cleanup & Summary
# The sensor ensures cleanup only runs after ALL frames are processed
