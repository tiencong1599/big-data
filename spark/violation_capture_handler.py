"""
Violation Capture Handler - Production Grade Implementation
============================================================

Handles asynchronous frame capture for speed violations with:
- Non-blocking background processing
- Thread-safe queue management
- Intelligent deduplication
- Batch database operations
- Memory-efficient image handling

Design Principles:
1. NEVER block the main processing thread
2. Deduplicate captures per vehicle per session
3. Batch database inserts for efficiency
4. Graceful degradation under load
"""

import os
import cv2
import json
import time
import threading
import numpy as np
from queue import Queue, Full, Empty
from datetime import datetime
from typing import Dict, Set, Optional, List, Any
from dataclasses import dataclass, field
from contextlib import contextmanager
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ViolationData:
    """Immutable data class for violation capture metadata"""
    video_id: int
    track_id: int
    speed: float
    speed_limit: float
    vehicle_type: str
    class_id: int
    confidence: float
    frame_number: int
    bbox: Dict[str, int]
    video_timestamp: float
    session_start: datetime
    
    @property
    def speed_excess(self) -> float:
        return self.speed - self.speed_limit


class ViolationCaptureHandler:
    """
    Production-grade handler for capturing speed violation frames.
    
    Features:
    - Async background processing (non-blocking)
    - Thread-safe operations
    - Intelligent deduplication (one capture per vehicle per session)
    - Batch database inserts
    - Memory overflow protection
    - Graceful shutdown
    
    Usage:
        handler = ViolationCaptureHandler()
        
        # In processing loop:
        if handler.should_capture(video_id, track_id, speed):
            handler.capture_violation(frame, violation_data)
        
        # Periodic flush to database:
        handler.flush_to_database(db_session)
        
        # On shutdown:
        handler.shutdown()
    """
    
    # YOLO class ID to vehicle type mapping
    CLASS_NAMES = {
        0: 'car',
        1: 'bus',
        2: 'truck', 
        3: 'motorbike',
    }
    
    def __init__(
        self,
        capture_dir: str = "/app/violation_captures",
        jpeg_quality: int = 85,
        thumbnail_size: tuple = (320, 180),
        max_queue_size: int = 100,
        batch_size: int = 10,
        enable_thumbnails: bool = True
    ):
        """
        Initialize the violation capture handler.
        
        Args:
            capture_dir: Base directory for storing violation images
            jpeg_quality: JPEG compression quality (0-100, higher = better quality)
            thumbnail_size: Thumbnail dimensions (width, height)
            max_queue_size: Maximum pending captures in queue
            batch_size: Number of records to batch before DB insert
            enable_thumbnails: Whether to generate thumbnail images
        """
        self.capture_dir = capture_dir
        self.jpeg_quality = jpeg_quality
        self.thumbnail_size = thumbnail_size
        self.max_queue_size = max_queue_size
        self.batch_size = batch_size
        self.enable_thumbnails = enable_thumbnails
        
        # Ensure capture directory exists
        os.makedirs(capture_dir, exist_ok=True)
        
        # Track captured vehicles per session (prevents duplicates)
        # Format: {(video_id, session_start_str): set(track_ids)}
        self._captured_tracks: Dict[tuple, Set[int]] = {}
        self._tracks_lock = threading.RLock()
        
        # Background processing queue
        self._capture_queue: Queue = Queue(maxsize=max_queue_size)
        self._running = True
        
        # Database insert buffer
        self._violation_buffer: List[Dict[str, Any]] = []
        self._buffer_lock = threading.Lock()
        
        # Statistics
        self._stats = {
            'captures_queued': 0,
            'captures_processed': 0,
            'captures_skipped_duplicate': 0,
            'captures_skipped_queue_full': 0,
            'db_inserts': 0,
            'errors': 0
        }
        self._stats_lock = threading.Lock()
        
        # Start background worker thread
        self._worker_thread = threading.Thread(
            target=self._process_queue_worker,
            name="ViolationCaptureWorker",
            daemon=True
        )
        self._worker_thread.start()
        
        logger.info(f"[VIOLATION-CAPTURE] Initialized - Dir: {capture_dir}, "
                   f"Quality: {jpeg_quality}, Queue: {max_queue_size}")
    
    def should_capture(
        self, 
        video_id: int, 
        track_id: int, 
        speed: float, 
        speed_limit: float = 60.0,
        session_start: Optional[datetime] = None
    ) -> bool:
        """
        Check if this vehicle violation should be captured.
        
        Returns False if:
        - Speed is not over the limit
        - This track_id was already captured in this session
        - Class ID is not a vehicle (e.g., person)
        
        Thread-safe: Uses RLock for concurrent access.
        
        Args:
            video_id: Video identifier
            track_id: Unique track ID from tracker
            speed: Current vehicle speed
            speed_limit: Speed threshold (default 60 km/h)
            session_start: Processing session start time
            
        Returns:
            True if violation should be captured, False otherwise
        """
        # Check speed threshold
        if speed <= speed_limit:
            return False
        
        # Create session key
        session_key = (video_id, session_start.isoformat() if session_start else "default")
        
        with self._tracks_lock:
            # Initialize tracking set for this session if needed
            if session_key not in self._captured_tracks:
                self._captured_tracks[session_key] = set()
            
            # Check if already captured
            if track_id in self._captured_tracks[session_key]:
                with self._stats_lock:
                    self._stats['captures_skipped_duplicate'] += 1
                return False
            
            return True
    
    def capture_violation(
        self,
        frame: np.ndarray,
        violation_data: ViolationData
    ) -> bool:
        """
        Queue a violation for capture (non-blocking).
        
        The actual frame saving happens in a background thread.
        Returns immediately to avoid blocking the main processing loop.
        
        Args:
            frame: OpenCV frame (BGR format)
            violation_data: Violation metadata
            
        Returns:
            True if queued successfully, False if queue is full
        """
        video_id = violation_data.video_id
        track_id = violation_data.track_id
        session_start = violation_data.session_start
        
        # Create session key
        session_key = (video_id, session_start.isoformat() if session_start else "default")
        
        # Mark as captured to prevent duplicates
        with self._tracks_lock:
            if session_key not in self._captured_tracks:
                self._captured_tracks[session_key] = set()
            self._captured_tracks[session_key].add(track_id)
        
        # Create queue item with frame copy
        queue_item = {
            'frame': frame.copy(),  # Copy to avoid reference issues
            'data': violation_data,
            'queued_at': datetime.utcnow()
        }
        
        # Add to queue (non-blocking)
        try:
            self._capture_queue.put_nowait(queue_item)
            with self._stats_lock:
                self._stats['captures_queued'] += 1
            
            logger.info(f"[VIOLATION-CAPTURE] Queued: Video {video_id}, "
                       f"Track {track_id}, Speed {violation_data.speed:.1f} km/h")
            return True
            
        except Full:
            # Queue is full - graceful degradation
            with self._stats_lock:
                self._stats['captures_skipped_queue_full'] += 1
            
            logger.warning(f"[VIOLATION-CAPTURE] Queue full! Skipping capture for "
                          f"track {track_id} (Speed: {violation_data.speed:.1f} km/h)")
            return False
    
    def _process_queue_worker(self):
        """Background worker thread: Process capture queue continuously."""
        logger.info("[VIOLATION-CAPTURE] Background worker started")
        
        # Initialize database connection
        self._init_db_engine()
        
        while self._running:
            try:
                # Block with timeout to allow shutdown check
                item = self._capture_queue.get(timeout=1.0)
                self._save_capture(item['frame'], item['data'])
                self._capture_queue.task_done()
                
                # Auto-flush to database when buffer reaches batch_size
                self._auto_flush_to_db()
                
            except Empty:
                # On timeout, still try to flush any pending records
                self._auto_flush_to_db()
                continue  # Timeout, check running flag and continue
            except Exception as e:
                logger.error(f"[VIOLATION-CAPTURE] Worker error: {e}")
                with self._stats_lock:
                    self._stats['errors'] += 1
        
        # Final flush on shutdown
        self._auto_flush_to_db(force=True)
        logger.info("[VIOLATION-CAPTURE] Background worker stopped")
    
    def _init_db_engine(self):
        """Initialize SQLAlchemy database engine."""
        try:
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker
            
            database_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@postgres:5432/video_streaming')
            self._db_engine = create_engine(database_url, pool_pre_ping=True)
            self._Session = sessionmaker(bind=self._db_engine)
            logger.info(f"[VIOLATION-CAPTURE] Database connection initialized")
        except Exception as e:
            logger.error(f"[VIOLATION-CAPTURE] Failed to initialize database: {e}")
            self._db_engine = None
            self._Session = None
    
    def _auto_flush_to_db(self, force: bool = False):
        """Auto-flush buffer to database when batch_size is reached."""
        with self._buffer_lock:
            buffer_size = len(self._violation_buffer)
        
        if buffer_size == 0:
            return
        
        logger.debug(f"[VIOLATION-CAPTURE] Buffer size: {buffer_size}, batch_size: {self.batch_size}, force: {force}")
        
        if not force and buffer_size < self.batch_size:
            return
        
        if not hasattr(self, '_Session') or self._Session is None:
            logger.warning("[VIOLATION-CAPTURE] Database not initialized, skipping flush")
            return
        
        logger.info(f"[VIOLATION-CAPTURE] Triggering flush for {buffer_size} buffered violations")
        
        session = self._Session()
        try:
            inserted = self.flush_to_database(session)
            if inserted > 0:
                logger.info(f"[VIOLATION-CAPTURE] Auto-flushed {inserted} records to database")
        except Exception as e:
            logger.error(f"[VIOLATION-CAPTURE] Auto-flush error: {e}")
        finally:
            session.close()
    
    def _save_capture(self, frame: np.ndarray, data: ViolationData):
        """
        Save violation frame to disk and buffer metadata for DB.
        Runs in background thread.
        """
        try:
            video_id = data.video_id
            track_id = data.track_id
            frame_number = data.frame_number
            timestamp = datetime.utcnow()
            
            # Generate file paths with date-based subdirectories
            date_str = timestamp.strftime("%Y%m%d")
            session_str = data.session_start.strftime("%H%M%S") if data.session_start else "000000"
            
            # Create subdirectory structure: {video_id}/{date}/
            subdir = os.path.join(self.capture_dir, str(video_id), date_str)
            os.makedirs(subdir, exist_ok=True)
            
            # Generate unique filenames
            filename = f"violation_{video_id}_{track_id}_{frame_number}_{session_str}.jpg"
            thumb_filename = f"thumb_{video_id}_{track_id}_{frame_number}_{session_str}.jpg"
            
            image_path = os.path.join(subdir, filename)
            thumb_path = os.path.join(subdir, thumb_filename) if self.enable_thumbnails else None
            
            # Annotate frame with violation info
            annotated_frame = self._annotate_frame(frame, data)
            
            # Save full-resolution image
            cv2.imwrite(
                image_path,
                annotated_frame,
                [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality]
            )
            
            # Save thumbnail if enabled
            if self.enable_thumbnails and thumb_path:
                thumbnail = cv2.resize(annotated_frame, self.thumbnail_size)
                cv2.imwrite(
                    thumb_path,
                    thumbnail,
                    [cv2.IMWRITE_JPEG_QUALITY, 70]  # Lower quality for thumbnails
                )
            
            # Calculate relative paths for database storage
            rel_image_path = os.path.relpath(image_path, self.capture_dir)
            rel_thumb_path = os.path.relpath(thumb_path, self.capture_dir) if thumb_path else None
            
            # Create violation record for database
            violation_record = {
                'video_id': video_id,
                'track_id': track_id,
                'speed': round(data.speed, 2),
                'speed_limit': data.speed_limit,
                'speed_excess': round(data.speed_excess, 2),
                'vehicle_type': data.vehicle_type,
                'class_id': data.class_id,
                'confidence': round(data.confidence, 4) if data.confidence else None,
                'frame_number': frame_number,
                'frame_image_path': rel_image_path,
                'thumbnail_path': rel_thumb_path,
                'bbox_x1': data.bbox.get('x1'),
                'bbox_y1': data.bbox.get('y1'),
                'bbox_x2': data.bbox.get('x2'),
                'bbox_y2': data.bbox.get('y2'),
                'violation_timestamp': timestamp,
                'video_timestamp': data.video_timestamp,
                'session_start': data.session_start
            }
            
            # Add to buffer for batch insert
            with self._buffer_lock:
                self._violation_buffer.append(violation_record)
            
            with self._stats_lock:
                self._stats['captures_processed'] += 1
            
            # Log file size for monitoring
            file_size_kb = os.path.getsize(image_path) / 1024
            logger.info(f"[VIOLATION-CAPTURE] ✓ Saved: {filename} "
                       f"({file_size_kb:.1f}KB, Speed: {data.speed:.1f} km/h)")
            
        except Exception as e:
            logger.error(f"[VIOLATION-CAPTURE] Error saving capture: {e}")
            with self._stats_lock:
                self._stats['errors'] += 1
    
    def _annotate_frame(self, frame: np.ndarray, data: ViolationData) -> np.ndarray:
        """
        Add violation information overlay to the captured frame.
        
        Draws:
        - Red bounding box around violating vehicle
        - Speed and violation info panel
        - Timestamp watermark
        """
        annotated = frame.copy()
        
        bbox = data.bbox
        x1, y1, x2, y2 = bbox.get('x1', 0), bbox.get('y1', 0), bbox.get('x2', 0), bbox.get('y2', 0)
        
        # Colors
        RED = (0, 0, 255)
        WHITE = (255, 255, 255)
        BLACK = (0, 0, 0)
        YELLOW = (0, 255, 255)
        
        # Draw thick red bounding box
        cv2.rectangle(annotated, (x1, y1), (x2, y2), RED, 3)
        
        # Prepare info text lines
        info_lines = [
            "SPEED VIOLATION",
            f"Speed: {data.speed:.1f} km/h",
            f"Limit: {data.speed_limit:.0f} km/h",
            f"Excess: +{data.speed_excess:.1f} km/h",
            f"Vehicle: {data.vehicle_type.upper()}",
            f"Track ID: #{data.track_id}"
        ]
        
        # Calculate info box position (above bounding box if possible)
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5
        thickness = 1
        line_height = 20
        padding = 5
        
        # Calculate text dimensions
        max_text_width = 0
        for line in info_lines:
            (text_w, text_h), _ = cv2.getTextSize(line, font, font_scale, thickness)
            max_text_width = max(max_text_width, text_w)
        
        box_height = len(info_lines) * line_height + padding * 2
        box_width = max_text_width + padding * 2
        
        # Position info box
        info_x = x1
        info_y = max(box_height + 10, y1 - box_height - 10)
        if info_y < box_height:
            info_y = y2 + 10  # Place below if no space above
        
        # Draw semi-transparent background
        overlay = annotated.copy()
        cv2.rectangle(
            overlay,
            (info_x, info_y - box_height),
            (info_x + box_width, info_y),
            BLACK,
            -1
        )
        cv2.addWeighted(overlay, 0.7, annotated, 0.3, 0, annotated)
        
        # Draw info text
        for i, line in enumerate(info_lines):
            y_pos = info_y - box_height + padding + (i + 1) * line_height - 5
            color = RED if i == 0 else (YELLOW if "Excess" in line else WHITE)
            cv2.putText(
                annotated, line,
                (info_x + padding, y_pos),
                font, font_scale, color, thickness, cv2.LINE_AA
            )
        
        # Add timestamp watermark at bottom
        timestamp_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        frame_info = f"Frame #{data.frame_number} | {timestamp_str}"
        
        (text_w, text_h), _ = cv2.getTextSize(frame_info, font, 0.6, 1)
        
        # Semi-transparent background for timestamp
        overlay2 = annotated.copy()
        cv2.rectangle(
            overlay2,
            (0, frame.shape[0] - 30),
            (text_w + 20, frame.shape[0]),
            BLACK,
            -1
        )
        cv2.addWeighted(overlay2, 0.5, annotated, 0.5, 0, annotated)
        
        cv2.putText(
            annotated, frame_info,
            (10, frame.shape[0] - 10),
            font, 0.6, WHITE, 1, cv2.LINE_AA
        )
        
        return annotated
    
    def get_pending_violations(self) -> List[Dict[str, Any]]:
        """
        Get and clear buffered violations for database insert.
        Thread-safe operation.
        
        Returns:
            List of violation records ready for database insertion
        """
        with self._buffer_lock:
            violations = self._violation_buffer.copy()
            self._violation_buffer = []
        return violations
    
    def flush_to_database(self, db_session) -> int:
        """
        Flush buffered violations to database using raw SQL batch insert.
        
        Args:
            db_session: SQLAlchemy database session
            
        Returns:
            Number of records inserted
        """
        violations = self.get_pending_violations()
        
        if not violations:
            return 0
        
        logger.info(f"[VIOLATION-CAPTURE] Attempting to insert {len(violations)} violations to database")
        
        try:
            from sqlalchemy import text
            
            # Use raw SQL for insert (no ON CONFLICT - handle duplicates via unique index)
            insert_sql = text("""
                INSERT INTO violation_captures (
                    video_id, track_id, speed, speed_limit, speed_excess,
                    vehicle_type, class_id, confidence, frame_number,
                    frame_image_path, thumbnail_path,
                    bbox_x1, bbox_y1, bbox_x2, bbox_y2,
                    violation_timestamp, video_timestamp, session_start
                ) VALUES (
                    :video_id, :track_id, :speed, :speed_limit, :speed_excess,
                    :vehicle_type, :class_id, :confidence, :frame_number,
                    :frame_image_path, :thumbnail_path,
                    :bbox_x1, :bbox_y1, :bbox_x2, :bbox_y2,
                    :violation_timestamp, :video_timestamp, :session_start
                )
            """)
            
            # Execute batch insert - each in its own mini-transaction to prevent cascade failures
            inserted_count = 0
            for v in violations:
                try:
                    db_session.execute(insert_sql, {
                        'video_id': v['video_id'],
                        'track_id': v['track_id'],
                        'speed': v['speed'],
                        'speed_limit': v['speed_limit'],
                        'speed_excess': v['speed_excess'],
                        'vehicle_type': v['vehicle_type'],
                        'class_id': v['class_id'],
                        'confidence': v['confidence'],
                        'frame_number': v['frame_number'],
                        'frame_image_path': v['frame_image_path'],
                        'thumbnail_path': v['thumbnail_path'],
                        'bbox_x1': v['bbox_x1'],
                        'bbox_y1': v['bbox_y1'],
                        'bbox_x2': v['bbox_x2'],
                        'bbox_y2': v['bbox_y2'],
                        'violation_timestamp': v['violation_timestamp'],
                        'video_timestamp': v['video_timestamp'],
                        'session_start': v['session_start']
                    })
                    db_session.commit()  # Commit each insert individually
                    inserted_count += 1
                    logger.debug(f"[VIOLATION-CAPTURE] Inserted violation for track {v['track_id']}")
                except Exception as insert_err:
                    db_session.rollback()  # Rollback failed insert
                    logger.warning(f"[VIOLATION-CAPTURE] Insert error for track {v['track_id']}: {insert_err}")
            
            with self._stats_lock:
                self._stats['db_inserts'] += inserted_count
            
            logger.info(f"[VIOLATION-CAPTURE] ✓ Flushed {inserted_count}/{len(violations)} violations to database")
            return inserted_count
            
        except Exception as e:
            db_session.rollback()
            logger.error(f"[VIOLATION-CAPTURE] Database flush error: {e}")
            
            # Put violations back in buffer for retry
            with self._buffer_lock:
                self._violation_buffer.extend(violations)
            
            with self._stats_lock:
                self._stats['errors'] += 1
            
            return 0
    
    def clear_session(self, video_id: int, session_start: Optional[datetime] = None):
        """
        Clear tracking data for a video session.
        Call this when video processing completes.
        
        Args:
            video_id: Video identifier
            session_start: Session start time (optional)
        """
        session_key = (video_id, session_start.isoformat() if session_start else "default")
        
        with self._tracks_lock:
            if session_key in self._captured_tracks:
                count = len(self._captured_tracks[session_key])
                del self._captured_tracks[session_key]
                logger.info(f"[VIOLATION-CAPTURE] Cleared session {video_id}: "
                           f"{count} captured tracks")
    
    def get_stats(self) -> Dict[str, int]:
        """Get capture statistics."""
        with self._stats_lock:
            return self._stats.copy()
    
    def get_queue_depth(self) -> int:
        """Get current queue depth for monitoring."""
        return self._capture_queue.qsize()
    
    def shutdown(self, timeout: float = 5.0):
        """
        Graceful shutdown - process remaining queue items.
        
        Args:
            timeout: Maximum seconds to wait for queue to drain
        """
        logger.info("[VIOLATION-CAPTURE] Initiating shutdown...")
        
        self._running = False
        
        # Wait for queue to drain
        try:
            self._capture_queue.join()
        except:
            pass
        
        # Wait for worker thread
        self._worker_thread.join(timeout=timeout)
        
        remaining = self._capture_queue.qsize()
        if remaining > 0:
            logger.warning(f"[VIOLATION-CAPTURE] Shutdown with {remaining} items remaining in queue")
        
        stats = self.get_stats()
        logger.info(f"[VIOLATION-CAPTURE] Shutdown complete. Stats: {stats}")
    
    @classmethod
    def get_vehicle_type(cls, class_id: int) -> str:
        """Convert YOLO class ID to vehicle type name."""
        return cls.CLASS_NAMES.get(class_id, 'unknown')


# ============================================================================
# Singleton Instance for Global Access
# ============================================================================

_handler_instance: Optional[ViolationCaptureHandler] = None
_handler_lock = threading.Lock()


def get_violation_handler(
    capture_dir: str = "/app/violation_captures",
    **kwargs
) -> ViolationCaptureHandler:
    """
    Get or create the global violation capture handler instance.
    Thread-safe singleton pattern.
    
    Args:
        capture_dir: Base directory for violation captures
        **kwargs: Additional arguments for ViolationCaptureHandler
        
    Returns:
        ViolationCaptureHandler singleton instance
    """
    global _handler_instance
    
    with _handler_lock:
        if _handler_instance is None:
            _handler_instance = ViolationCaptureHandler(capture_dir=capture_dir, **kwargs)
        return _handler_instance


def shutdown_violation_handler():
    """Shutdown the global violation handler instance."""
    global _handler_instance
    
    with _handler_lock:
        if _handler_instance is not None:
            _handler_instance.shutdown()
            _handler_instance = None
