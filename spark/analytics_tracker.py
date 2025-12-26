# spark/analytics_tracker.py (NEW FILE)

import redis
import json
import time
from typing import Dict, Set

class VehicleAnalyticsTracker:
    """
    Track vehicle metrics in Redis during real-time processing
    Dump to PostgreSQL when video processing completes
    """
    
    def __init__(self, redis_client: redis.Redis, video_id: int):
        self.redis = redis_client
        self.video_id = video_id
        self.redis_key = f"analytics:video:{video_id}"
        
        # Initialize counters
        self.total_vehicles_entered = 0
        self.current_vehicles_in_roi: Set[int] = set()
        self.vehicle_enter_times: Dict[int, float] = {}
        self.vehicle_types: Dict[int, str] = {}
        
        print(f"[ANALYTICS] Tracker initialized for video {video_id}")
    
    def _write_to_redis(self):
        """Write current metrics to Redis (in-memory cache)"""
        metrics = {
            'video_id': self.video_id,
            'total_vehicles_count': self.total_vehicles_entered,
            'current_vehicles_count': len(self.current_vehicles_in_roi),
            'updated_at': time.time()
        }
        
        self.redis.set(
            self.redis_key,
            json.dumps(metrics),
            ex=86400  # Expire after 24 hours
        )
    
    def update(self, tracks, frame_timestamp):
        """Update analytics with current frame tracks"""
        current_track_ids = {track_id for track_id, _ in tracks}
        
        # Detect new vehicles entering ROI
        new_vehicles = current_track_ids - self.current_vehicles_in_roi
        
        for track_id in new_vehicles:
            self.total_vehicles_entered += 1
            self.vehicle_enter_times[track_id] = frame_timestamp
            self.current_vehicles_in_roi.add(track_id)
        
        # Detect vehicles exiting ROI
        exited_vehicles = self.current_vehicles_in_roi - current_track_ids
        for track_id in exited_vehicles:
            self.current_vehicles_in_roi.discard(track_id)
            self.vehicle_enter_times.pop(track_id, None)
        
        # Write to Redis on EVERY update (ensures final count is always saved)
        self._write_to_redis()
    
    def set_vehicle_type(self, track_id: int, class_id: int):
        """Map YOLO class_id to vehicle type"""
        class_names = {
            2: 'car',
            7: 'truck',
            3: 'motorcycle',
            5: 'bus',
            1: 'bicycle'
        }
        self.vehicle_types[track_id] = class_names.get(class_id, 'unknown')
    
    def _record_vehicle_exit(self, track_id: int, dwell_time: float):
        """Record vehicle exit metrics"""
        vehicle_type = self.vehicle_types.get(track_id, 'unknown')
        
        # Store in Redis list
        exit_data = {
            'track_id': track_id,
            'dwell_time': round(dwell_time, 2),
            'vehicle_type': vehicle_type,
            'exit_timestamp': time.time()
        }
        
        self.redis.rpush(
            f"{self.redis_key}:exits",
            json.dumps(exit_data)
        )
        
        print(f"[ANALYTICS] Vehicle {track_id} exited ROI (dwell: {dwell_time:.1f}s, type: {vehicle_type})")
    
    def get_current_metrics(self):
        """Get current analytics metrics for this frame"""
        return {
            'total_vehicles_entered': self.total_vehicles_entered,
            'current_vehicles_in_roi': len(self.current_vehicles_in_roi)
        }
    
    def finalize_and_dump_to_db(self, db_session):
        """
        Called when video processing completes
        Dump all metrics from Redis to PostgreSQL
        """
        try:
            # Retrieve metrics from Redis
            metrics_json = self.redis.get(self.redis_key)
            if not metrics_json:
                print(f"[ANALYTICS] No metrics found for video {self.video_id}")
                return
            
            metrics = json.loads(metrics_json)
            
            # Retrieve exit records
            exit_records = []
            exits_key = f"{self.redis_key}:exits"
            for i in range(self.redis.llen(exits_key)):
                exit_data = self.redis.lindex(exits_key, i)
                if exit_data:
                    exit_records.append(json.loads(exit_data))
            
            # Calculate average dwell time
            avg_dwell_time = 0
            if exit_records:
                avg_dwell_time = sum(r['dwell_time'] for r in exit_records) / len(exit_records)
            
            # Insert into PostgreSQL
            from models.video import VideoAnalytics
            
            analytics = VideoAnalytics(
                video_id=self.video_id,
                total_vehicles_count=metrics['total_vehicles_count'],
                avg_dwell_time=round(avg_dwell_time, 2),
                vehicle_type_distribution=json.dumps(self._get_type_distribution(exit_records)),
                processed_at=metrics['updated_at']
            )
            
            db_session.add(analytics)
            db_session.commit()
            
            print(f"[ANALYTICS] ✓ Dumped metrics to DB for video {self.video_id}")
            print(f"   Total vehicles: {metrics['total_vehicles_count']}")
            print(f"   Avg dwell time: {avg_dwell_time:.2f}s")
            
            # Clean up Redis data
            self.redis.delete(self.redis_key)
            self.redis.delete(exits_key)
            print(f"[ANALYTICS] ✓ Cleaned up Redis data")
        
        except Exception as e:
            print(f"[ANALYTICS] ❌ Error dumping to DB: {e}")
            db_session.rollback()
    
    def _get_type_distribution(self, exit_records):
        """Calculate vehicle type distribution"""
        distribution = {}
        for record in exit_records:
            vtype = record['vehicle_type']
            distribution[vtype] = distribution.get(vtype, 0) + 1
        return distribution