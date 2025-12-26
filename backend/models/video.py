from sqlalchemy import Column, Integer, String, DateTime, JSON, Float, ForeignKey, TIMESTAMP
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
from database import engine, get_db

Base = declarative_base()

class Video(Base):
    __tablename__ = 'video'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    roi = Column(JSON, nullable=True)  # ROI polygon coordinates
    calibrate_coordinates = Column(JSON, nullable=True)  # Camera calibration data
    homography_matrix = Column(JSON, nullable=True)  # Homography matrix H
    camera_matrix = Column(JSON, nullable=True)  # Camera intrinsic matrix K
    fps = Column(Float, nullable=True)  # Video FPS
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'file_path': self.file_path,
            'roi': self.roi,
            'calibrate_coordinates': self.calibrate_coordinates,
            'homography_matrix': self.homography_matrix,
            'camera_matrix': self.camera_matrix,
            'fps': self.fps,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)

def get_video_config(video_id):
    """
    Get video configuration for processing from database
    Returns configuration needed for Spark processing
    """
    db = get_db()
    try:
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            return None
        
        # Extract ROI polygon from roi JSON field
        roi_polygon = None
        if video.roi:
            # ROI can be stored as {"roi_polygon": [[x1,y1], [x2,y2], ...]}
            # or {"x": 100, "y": 100, "width": 500, "height": 300}
            if isinstance(video.roi, dict):
                if 'roi_polygon' in video.roi:
                    roi_polygon = video.roi['roi_polygon']
                elif 'x' in video.roi and 'y' in video.roi:
                    # Convert rectangle format to polygon
                    x = video.roi['x']
                    y = video.roi['y']
                    w = video.roi.get('width', 500)
                    h = video.roi.get('height', 300)
                    roi_polygon = [
                        [x, y],
                        [x + w, y],
                        [x + w, y + h],
                        [x, y + h]
                    ]
        
        return {
            'video_id': video.id,
            'roi_polygon': roi_polygon,
            'homography_matrix': video.homography_matrix,
            'camera_matrix': video.camera_matrix,
            'fps': video.fps or 30.0,
            'use_roi': roi_polygon is not None and len(roi_polygon) > 0,
            'use_homography': video.homography_matrix is not None
        }
    finally:
        db.close()

# ============================================================================
# PHASE 3: Analytics Models for Historical Storage
# ============================================================================

class VideoAnalyticsSnapshot(Base):
    """Periodic snapshots of real-time analytics for trend analysis"""
    __tablename__ = 'video_analytics_snapshots'
    
    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey('video.id', ondelete='CASCADE'), nullable=False)
    frame_number = Column(Integer, nullable=False)
    timestamp = Column(Float, nullable=False)
    
    # Frame-level stats
    total_vehicles = Column(Integer, default=0)
    speeding_count = Column(Integer, default=0)
    current_in_roi = Column(Integer, default=0)
    
    # Session metadata
    session_start = Column(TIMESTAMP)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'video_id': self.video_id,
            'frame_number': self.frame_number,
            'timestamp': self.timestamp,
            'total_vehicles': self.total_vehicles,
            'speeding_count': self.speeding_count,
            'current_in_roi': self.current_in_roi,
            'session_start': self.session_start.isoformat() if self.session_start else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class SpeedingVehicle(Base):
    """Individual speeding vehicle records for compliance and audit"""
    __tablename__ = 'speeding_vehicles'
    
    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey('video.id', ondelete='CASCADE'), nullable=False)
    
    # Vehicle identification
    track_id = Column(Integer, nullable=False)
    
    # Speed data
    speed = Column(Float, nullable=False)
    speed_unit = Column(String(10), default='km/h')
    
    # Vehicle classification
    class_id = Column(Integer, nullable=False)
    class_name = Column(String(50))
    confidence = Column(Float)
    
    # Detection metadata
    frame_number = Column(Integer, nullable=False)
    timestamp = Column(Float, nullable=False)
    detected_at = Column(TIMESTAMP, default=datetime.utcnow)
    
    # Session tracking
    session_start = Column(TIMESTAMP)
    
    def to_dict(self):
        return {
            'id': self.id,
            'video_id': self.video_id,
            'track_id': self.track_id,
            'speed': self.speed,
            'speed_unit': self.speed_unit,
            'class_id': self.class_id,
            'class_name': self.class_name,
            'confidence': self.confidence,
            'frame_number': self.frame_number,
            'timestamp': self.timestamp,
            'detected_at': self.detected_at.isoformat() if self.detected_at else None,
            'session_start': self.session_start.isoformat() if self.session_start else None
        }


class ViolationCapture(Base):
    """
    Captured frames and metadata for speed violations.
    Stores violation evidence with annotated frame images.
    """
    __tablename__ = 'violation_captures'
    
    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey('video.id', ondelete='CASCADE'), nullable=False)
    
    # Vehicle identification
    track_id = Column(Integer, nullable=False)
    
    # Speed violation data
    speed = Column(Float, nullable=False)  # Actual speed in km/h
    speed_limit = Column(Float, nullable=False, default=60.0)  # Speed limit threshold
    speed_excess = Column(Float, nullable=False)  # Amount over limit
    
    # Vehicle classification
    vehicle_type = Column(String(50), nullable=False)  # car, truck, bus, motorcycle
    class_id = Column(Integer, nullable=False)  # YOLO class ID
    confidence = Column(Float)  # Detection confidence
    
    # Frame capture data
    frame_number = Column(Integer, nullable=False)
    frame_image_path = Column(String(500), nullable=False)  # Relative path to image
    thumbnail_path = Column(String(500))  # Relative path to thumbnail
    
    # Bounding box coordinates
    bbox_x1 = Column(Integer)
    bbox_y1 = Column(Integer)
    bbox_x2 = Column(Integer)
    bbox_y2 = Column(Integer)
    
    # Timestamps
    violation_timestamp = Column(TIMESTAMP, nullable=False)  # When violation occurred
    video_timestamp = Column(Float)  # Timestamp within video
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    
    # Session tracking
    session_start = Column(TIMESTAMP)
    
    def to_dict(self):
        return {
            'id': self.id,
            'video_id': self.video_id,
            'track_id': self.track_id,
            'speed': self.speed,
            'speed_limit': self.speed_limit,
            'speed_excess': self.speed_excess,
            'vehicle_type': self.vehicle_type,
            'class_id': self.class_id,
            'confidence': self.confidence,
            'frame_number': self.frame_number,
            'frame_image_path': self.frame_image_path,
            'thumbnail_path': self.thumbnail_path,
            'bbox': {
                'x1': self.bbox_x1,
                'y1': self.bbox_y1,
                'x2': self.bbox_x2,
                'y2': self.bbox_y2
            },
            'violation_timestamp': self.violation_timestamp.isoformat() if self.violation_timestamp else None,
            'video_timestamp': self.video_timestamp,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'session_start': self.session_start.isoformat() if self.session_start else None
        }


class VideoAnalyticsSummary(Base):
    """Final aggregated analytics after video processing completes"""
    __tablename__ = 'video_analytics_summary'
    
    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey('video.id', ondelete='CASCADE'), nullable=False)
    
    # Aggregated counts
    total_vehicles_detected = Column(Integer, default=0)
    total_speeding_violations = Column(Integer, default=0)
    max_concurrent_vehicles = Column(Integer, default=0)
    
    # Performance metrics
    avg_processing_fps = Column(Float)
    total_frames_processed = Column(Integer)
    
    # Vehicle type distribution
    vehicle_type_distribution = Column(JSON)
    
    # Speed statistics
    avg_speed = Column(Float)
    max_speed = Column(Float)
    speed_distribution = Column(JSON)
    
    # Session metadata
    session_start = Column(TIMESTAMP)
    session_end = Column(TIMESTAMP)
    processing_duration_seconds = Column(Integer)
    
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'video_id': self.video_id,
            'total_vehicles_detected': self.total_vehicles_detected,
            'total_speeding_violations': self.total_speeding_violations,
            'max_concurrent_vehicles': self.max_concurrent_vehicles,
            'avg_processing_fps': self.avg_processing_fps,
            'total_frames_processed': self.total_frames_processed,
            'vehicle_type_distribution': self.vehicle_type_distribution,
            'avg_speed': self.avg_speed,
            'max_speed': self.max_speed,
            'speed_distribution': self.speed_distribution,
            'session_start': self.session_start.isoformat() if self.session_start else None,
            'session_end': self.session_end.isoformat() if self.session_end else None,
            'processing_duration_seconds': self.processing_duration_seconds,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
