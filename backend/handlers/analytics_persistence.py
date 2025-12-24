"""
Analytics Persistence Handler - Phase 3
Asynchronously persists analytics data to PostgreSQL without impacting real-time performance
"""
import logging
import asyncio
import json
from datetime import datetime
from typing import Dict, Any, Optional
from models.video import get_db, VideoAnalyticsSnapshot, SpeedingVehicle, VideoAnalyticsSummary

logger = logging.getLogger(__name__)


class AnalyticsPersistenceHandler:
    """
    Handles asynchronous persistence of analytics data to database
    
    Design principles:
    - Non-blocking: Uses asyncio for database writes
    - Batching: Accumulates records before bulk insert
    - Sampling: Only persists snapshots at intervals (not every frame)
    - Zero impact: Runs in background thread, doesn't affect WebSocket performance
    """
    
    def __init__(self, snapshot_interval_seconds: int = 10):
        """
        Initialize analytics persistence handler
        
        Args:
            snapshot_interval_seconds: How often to persist snapshots (default: 10s)
        """
        self.snapshot_interval = snapshot_interval_seconds
        self.last_snapshot_time: Dict[int, float] = {}  # video_id -> last_snapshot_timestamp
        self.speeding_vehicle_buffer: Dict[int, list] = {}  # video_id -> [vehicles]
        self.session_start_times: Dict[int, datetime] = {}  # video_id -> session_start
        self.running = True
        
        # Performance counters
        self.snapshots_saved = 0
        self.vehicles_saved = 0
        
        logger.info(f"Analytics persistence initialized (snapshot interval: {snapshot_interval_seconds}s)")
    
    async def persist_analytics_snapshot(self, analytics_data: Dict[str, Any]) -> None:
        """
        Persist analytics snapshot if interval has elapsed
        
        Args:
            analytics_data: AnalyticsData from WebSocket
                {
                    'video_id': int,
                    'frame_number': int,
                    'timestamp': float,
                    'stats': {'total_vehicles': int, 'speeding_count': int, 'current_in_roi': int},
                    'speeding_vehicles': [...]
                }
        """
        try:
            video_id = analytics_data.get('video_id')
            timestamp = analytics_data.get('timestamp', 0.0)
            
            if not video_id:
                return
            
            # Initialize session start time if first message
            if video_id not in self.session_start_times:
                self.session_start_times[video_id] = datetime.utcnow()
            
            # Check if we should persist a snapshot (rate limiting)
            last_time = self.last_snapshot_time.get(video_id, 0)
            if timestamp - last_time < self.snapshot_interval:
                # Too soon, skip snapshot (but still check for speeding vehicles)
                await self._buffer_speeding_vehicles(analytics_data)
                return
            
            # Time to persist a snapshot
            self.last_snapshot_time[video_id] = timestamp
            
            stats = analytics_data.get('stats', {})
            snapshot = VideoAnalyticsSnapshot(
                video_id=video_id,
                frame_number=analytics_data.get('frame_number', 0),
                timestamp=timestamp,
                total_vehicles=stats.get('total_vehicles', 0),
                speeding_count=stats.get('speeding_count', 0),
                current_in_roi=stats.get('current_in_roi', 0),
                session_start=self.session_start_times[video_id]
            )
            
            # Non-blocking database insert
            await asyncio.to_thread(self._save_snapshot, snapshot)
            self.snapshots_saved += 1
            
            # Also persist speeding vehicles
            await self._buffer_speeding_vehicles(analytics_data)
            
        except Exception as e:
            logger.error(f"Error persisting analytics snapshot: {e}", exc_info=True)
    
    async def _buffer_speeding_vehicles(self, analytics_data: Dict[str, Any]) -> None:
        """Buffer speeding vehicles for batch insertion"""
        try:
            video_id = analytics_data.get('video_id')
            speeding_vehicles = analytics_data.get('speeding_vehicles', [])
            
            if not speeding_vehicles:
                return
            
            # Initialize buffer
            if video_id not in self.speeding_vehicle_buffer:
                self.speeding_vehicle_buffer[video_id] = []
            
            # Add new vehicles to buffer
            for vehicle in speeding_vehicles:
                vehicle_record = SpeedingVehicle(
                    video_id=video_id,
                    track_id=vehicle.get('track_id'),
                    speed=vehicle.get('speed', 0.0),
                    speed_unit='km/h',
                    class_id=vehicle.get('class_id', 0),
                    class_name=vehicle.get('class_name', 'unknown'),
                    confidence=vehicle.get('confidence', 0.0),
                    frame_number=analytics_data.get('frame_number', 0),
                    timestamp=analytics_data.get('timestamp', 0.0),
                    session_start=self.session_start_times.get(video_id)
                )
                self.speeding_vehicle_buffer[video_id].append(vehicle_record)
            
            # Batch insert if buffer is large enough (>= 10 vehicles)
            if len(self.speeding_vehicle_buffer[video_id]) >= 10:
                await self._flush_speeding_vehicles(video_id)
                
        except Exception as e:
            logger.error(f"Error buffering speeding vehicles: {e}", exc_info=True)
    
    async def _flush_speeding_vehicles(self, video_id: int) -> None:
        """Flush buffered speeding vehicles to database"""
        try:
            buffer = self.speeding_vehicle_buffer.get(video_id, [])
            if not buffer:
                return
            
            # Bulk insert in background thread
            await asyncio.to_thread(self._save_vehicles_bulk, buffer)
            
            self.vehicles_saved += len(buffer)
            logger.debug(f"Flushed {len(buffer)} speeding vehicles for video {video_id}")
            
            # Clear buffer
            self.speeding_vehicle_buffer[video_id] = []
            
        except Exception as e:
            logger.error(f"Error flushing speeding vehicles: {e}", exc_info=True)
    
    def _save_snapshot(self, snapshot: VideoAnalyticsSnapshot) -> None:
        """Synchronous database save (called in thread pool)"""
        db = get_db()
        try:
            db.add(snapshot)
            db.commit()
            logger.debug(f"Saved snapshot for video {snapshot.video_id} at frame {snapshot.frame_number}")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to save snapshot: {e}")
        finally:
            db.close()
    
    def _save_vehicles_bulk(self, vehicles: list) -> None:
        """Synchronous bulk insert (called in thread pool)"""
        db = get_db()
        try:
            db.bulk_save_objects(vehicles)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to bulk insert vehicles: {e}")
        finally:
            db.close()
    
    async def finalize_session(self, video_id: int) -> None:
        """
        Finalize video session: flush remaining data and create summary
        Called when video stream ends
        """
        try:
            logger.info(f"Finalizing analytics session for video {video_id}")
            
            # Flush any remaining buffered vehicles
            await self._flush_speeding_vehicles(video_id)
            
            # Create summary (optional - can be done by Airflow cleanup task)
            # await self._create_session_summary(video_id)
            
            # Cleanup session state
            self.last_snapshot_time.pop(video_id, None)
            self.speeding_vehicle_buffer.pop(video_id, None)
            self.session_start_times.pop(video_id, None)
            
            logger.info(f"Session finalized for video {video_id}")
            
        except Exception as e:
            logger.error(f"Error finalizing session: {e}", exc_info=True)
    
    def get_stats(self) -> Dict[str, int]:
        """Get persistence statistics"""
        return {
            'snapshots_saved': self.snapshots_saved,
            'vehicles_saved': self.vehicles_saved,
            'active_sessions': len(self.session_start_times),
            'buffered_vehicles': sum(len(buf) for buf in self.speeding_vehicle_buffer.values())
        }
    
    async def stop(self) -> None:
        """Graceful shutdown: flush all buffers"""
        logger.info("Shutting down analytics persistence...")
        self.running = False
        
        # Flush all buffered data
        for video_id in list(self.speeding_vehicle_buffer.keys()):
            await self._flush_speeding_vehicles(video_id)
        
        stats = self.get_stats()
        logger.info(f"Analytics persistence stopped. Final stats: {stats}")


# Global singleton instance
_persistence_handler: Optional[AnalyticsPersistenceHandler] = None


def get_persistence_handler() -> AnalyticsPersistenceHandler:
    """Get or create global persistence handler instance"""
    global _persistence_handler
    if _persistence_handler is None:
        _persistence_handler = AnalyticsPersistenceHandler(snapshot_interval_seconds=10)
    return _persistence_handler
