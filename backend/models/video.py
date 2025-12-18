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
    
    # Relationship
    analytics = relationship("VideoAnalytics", back_populates="video", cascade="all, delete-orphan")

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

# NEW TABLE: VideoAnalytics
class VideoAnalytics(Base):
    __tablename__ = 'video_analytics'
    
    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey('video.id'), nullable=False)
    total_vehicles_count = Column(Integer, default=0)
    avg_dwell_time = Column(Float, default=0.0)  # seconds
    vehicle_type_distribution = Column(JSON, nullable=True)  # {"car": 10, "truck": 5, ...}
    processed_at = Column(Float, nullable=False)  # Unix timestamp
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    
    # Relationship
    video = relationship("Video", back_populates="analytics")
