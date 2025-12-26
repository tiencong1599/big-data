"""
Generate analytics summary from existing snapshot and speeding vehicle data
This script creates VideoAnalyticsSummary records from the raw analytics data
"""
import sys
from sqlalchemy import func
from datetime import datetime
from models.video import VideoAnalyticsSnapshot, SpeedingVehicle, VideoAnalyticsSummary
from database import get_db

def generate_summary_for_session(video_id: int, session_start: datetime):
    """Generate summary for a specific session"""
    db = get_db()
    
    try:
        # Get snapshot data for this session
        snapshots = db.query(VideoAnalyticsSnapshot).filter(
            VideoAnalyticsSnapshot.video_id == video_id,
            VideoAnalyticsSnapshot.session_start == session_start
        ).all()
        
        if not snapshots:
            print(f"No snapshots found for video {video_id}, session {session_start}")
            return None
        
        # Get speeding vehicles for this session
        speeding_vehicles = db.query(SpeedingVehicle).filter(
            SpeedingVehicle.video_id == video_id,
            SpeedingVehicle.session_start == session_start
        ).all()
        
        # Calculate aggregated metrics
        total_vehicles = max([s.total_vehicles for s in snapshots]) if snapshots else 0
        total_speeding = len(set(v.track_id for v in speeding_vehicles))  # Unique vehicles
        max_concurrent = max([s.current_in_roi for s in snapshots]) if snapshots else 0
        total_frames = max([s.frame_number for s in snapshots]) if snapshots else 0
        
        # Get session end time (last snapshot timestamp)
        session_end = snapshots[-1].created_at if snapshots else session_start
        
        # Calculate processing duration
        duration_seconds = int((session_end - session_start).total_seconds())
        
        # Calculate average FPS
        avg_fps = total_frames / duration_seconds if duration_seconds > 0 else 0
        
        # Group by track_id and get max speed for each unique vehicle
        vehicle_max_speeds = {}
        vehicle_class_names = {}
        for v in speeding_vehicles:
            if v.track_id not in vehicle_max_speeds or v.speed > vehicle_max_speeds[v.track_id]:
                vehicle_max_speeds[v.track_id] = v.speed
                vehicle_class_names[v.track_id] = v.class_name or 'unknown'
        
        # Calculate speed statistics from unique vehicles
        unique_speeds = list(vehicle_max_speeds.values())
        avg_speed = sum(unique_speeds) / len(unique_speeds) if unique_speeds else 0
        max_speed = max(unique_speeds) if unique_speeds else 0
        
        # Speed distribution (buckets: 60-70, 70-80, 80-90, 90+) - unique vehicles
        speed_distribution = {
            'range_60_70': len([s for s in unique_speeds if 60 <= s < 70]),
            'range_70_80': len([s for s in unique_speeds if 70 <= s < 80]),
            'range_80_90': len([s for s in unique_speeds if 80 <= s < 90]),
            'range_90_plus': len([s for s in unique_speeds if s >= 90])
        }
        
        # Vehicle type distribution - unique vehicles
        vehicle_types = {}
        for track_id, class_name in vehicle_class_names.items():
            vehicle_types[class_name] = vehicle_types.get(class_name, 0) + 1
        
        # Create summary record
        summary = VideoAnalyticsSummary(
            video_id=video_id,
            total_vehicles_detected=total_vehicles,
            total_speeding_violations=total_speeding,
            max_concurrent_vehicles=max_concurrent,
            avg_processing_fps=avg_fps,
            total_frames_processed=total_frames,
            vehicle_type_distribution=vehicle_types,
            avg_speed=avg_speed,
            max_speed=max_speed,
            speed_distribution=speed_distribution,
            session_start=session_start,
            session_end=session_end,
            processing_duration_seconds=duration_seconds
        )
        
        db.add(summary)
        db.commit()
        
        print(f"✓ Created summary for video {video_id}, session {session_start}")
        print(f"  - Total vehicles: {total_vehicles}")
        print(f"  - Speeding violations: {total_speeding}")
        print(f"  - Max concurrent: {max_concurrent}")
        print(f"  - Avg FPS: {avg_fps:.2f}")
        print(f"  - Duration: {duration_seconds}s")
        
        return summary
        
    except Exception as e:
        db.rollback()
        print(f"✗ Error generating summary: {e}")
        raise
    finally:
        db.close()


def generate_all_summaries():
    """Generate summaries for all sessions"""
    db = get_db()
    
    try:
        # Get all unique sessions (video_id, session_start combinations)
        sessions = db.query(
            VideoAnalyticsSnapshot.video_id,
            VideoAnalyticsSnapshot.session_start
        ).distinct().all()
        
        print(f"Found {len(sessions)} unique sessions")
        print("=" * 60)
        
        for video_id, session_start in sessions:
            generate_summary_for_session(video_id, session_start)
            print("-" * 60)
        
        print(f"\n✓ Successfully generated {len(sessions)} summaries")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == '__main__':
    print("Analytics Summary Generator")
    print("=" * 60)
    generate_all_summaries()
