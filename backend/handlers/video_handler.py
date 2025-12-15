import tornado.web
import tornado.escape
import json
import os
import uuid
import logging
import numpy as np
import cv2
from models.video import get_db, Video
from config.settings import VIDEO_STORAGE_PATH, ALLOWED_ORIGINS

logger = logging.getLogger(__name__)

def compute_homography_from_calibration(calibrate_data):
    """
    Compute homography matrix from calibration coordinates.
    
    Args:
        calibrate_data (dict): {
            'points': [
                {'pixel': [x, y], 'real': [X, Y]},
                ...
            ]
        }
    
    Returns:
        list: 3x3 homography matrix as nested list, or None if computation fails
    """
    if not calibrate_data or 'points' not in calibrate_data:
        logger.warning("No calibration points provided")
        return None
    
    points = calibrate_data['points']
    if len(points) < 4:
        logger.warning(f"Insufficient calibration points: {len(points)} (need at least 4)")
        return None
    
    try:
        # Extract pixel (image) coordinates and real-world coordinates
        src_points = []  # Image coordinates
        dst_points = []  # Real-world coordinates
        
        for point in points:
            pixel = point['pixel']  # [x, y]
            real = point['real']    # [X, Y]
            src_points.append(pixel)
            dst_points.append(real)
        
        src_points = np.float32(src_points)
        dst_points = np.float32(dst_points)
        
        logger.info(f"Computing homography from {len(src_points)} point pairs")
        logger.info(f"  Image points: {src_points.tolist()}")
        logger.info(f"  World points: {dst_points.tolist()}")
        
        # Compute homography (image -> world)
        H, mask = cv2.findHomography(src_points, dst_points)
        
        if H is not None:
            logger.info("Homography matrix computed successfully:")
            logger.info(f"\n{H}")
            return H.tolist()  # Convert to list for JSON serialization
        else:
            logger.error("Failed to compute homography matrix")
            return None
            
    except Exception as e:
        logger.error(f"Error computing homography: {str(e)}", exc_info=True)
        return None

class BaseHandler(tornado.web.RequestHandler):
    def prepare(self):
        """Called at the beginning of every request"""
        logger.info(f"==> {self.request.method} {self.request.uri} from {self.request.remote_ip}")
        logger.info(f"    Origin: {self.request.headers.get('Origin', 'None')}")
    
    def set_default_headers(self):
        """Set CORS headers for ALL requests"""
        # Allow all origins during development
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "*")
        self.set_header("Access-Control-Max-Age", "0")
        
        logger.info(f"    CORS: Allowing all origins")
    
    def options(self, *args, **kwargs):
        """Handle OPTIONS preflight requests"""
        logger.info(f"==> OPTIONS (preflight) {self.request.uri}")
        self.set_status(204)
        self.finish()

class VideoUploadHandler(BaseHandler):
    async def post(self):
        """Handle video upload with metadata (ROI, calibration, homography, fps)"""
        try:
            logger.info("=== Video Upload Request Received ===")
            logger.info(f"Request from: {self.request.remote_ip}")
            
            # Get form data
            name = self.get_argument('name', None)
            roi = self.get_argument('roi', None)
            calibrate_coordinates = self.get_argument('calibrate_coordinates', None)
            homography_matrix = self.get_argument('homography_matrix', None)
            camera_matrix = self.get_argument('camera_matrix', None)
            fps = self.get_argument('fps', '30.0')
            
            logger.info(f"Video name: {name}")
            logger.info(f"Has ROI: {roi is not None}")
            logger.info(f"Has calibration: {calibrate_coordinates is not None}")
            
            if not name:
                logger.warning("Upload rejected: Video name is required")
                self.set_status(400)
                self.write({'error': 'Video name is required'})
                return
            
            # Get uploaded file
            if 'video' not in self.request.files:
                logger.warning("Upload rejected: No video file provided")
                self.set_status(400)
                self.write({'error': 'No video file provided'})
                return
            
            file_info = self.request.files['video'][0]
            filename = file_info['filename']
            file_body = file_info['body']
            
            logger.info(f"Received file: {filename} ({len(file_body)} bytes)")
            
            # Generate unique filename
            file_extension = os.path.splitext(filename)[1]
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            file_path = os.path.join(VIDEO_STORAGE_PATH, unique_filename)
            
            # Ensure video storage directory exists
            os.makedirs(VIDEO_STORAGE_PATH, exist_ok=True)
            
            # Save video file
            logger.info("Writing file to disk...")
            with open(file_path, 'wb') as f:
                f.write(file_body)
            logger.info(f"File saved successfully to: {file_path}")
            
            # Parse JSON fields
            logger.info("Parsing metadata...")
            roi_data = json.loads(roi) if roi else None
            calibrate_data = json.loads(calibrate_coordinates) if calibrate_coordinates else None
            homography_data = json.loads(homography_matrix) if homography_matrix else None
            camera_data = json.loads(camera_matrix) if camera_matrix else None
            fps_value = float(fps)
            
            # Compute homography matrix from calibration coordinates if provided
            if calibrate_data and not homography_data:
                logger.info("Computing homography matrix from calibration coordinates...")
                computed_homography = compute_homography_from_calibration(calibrate_data)
                if computed_homography:
                    homography_data = computed_homography
                    logger.info("✓ Homography matrix computed and will be stored")
                else:
                    logger.warning("✗ Failed to compute homography matrix - speed estimation will use identity matrix")
            
            # Save to database
            logger.info("Saving to database...")
            db = get_db()
            try:
                video = Video(
                    name=name,
                    file_path=file_path,
                    roi=roi_data,
                    calibrate_coordinates=calibrate_data,
                    homography_matrix=homography_data,
                    camera_matrix=camera_data,
                    fps=fps_value
                )
                db.add(video)
                db.commit()
                db.refresh(video)
                
                logger.info(f"Video saved to database with ID: {video.id}")
                logger.info("=== Upload Completed Successfully ===")
                
                self.set_status(201)
                self.write({
                    'message': 'Video uploaded successfully',
                    'video': video.to_dict()
                })
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Upload failed: {str(e)}", exc_info=True)
            self.set_status(500)
            self.write({'error': str(e)})

class VideoListHandler(BaseHandler):
    async def get(self):
        """Get list of all videos"""
        try:
            logger.info("=== Video List Request ===")
            self.set_header("Connection", "close")  # Force close connection after response
            db = get_db()
            try:
                videos = db.query(Video).all()
                video_list = [video.to_dict() for video in videos]
                
                logger.info(f"Returning {len(video_list)} videos")
                
                self.set_status(200)
                self.write({
                    'videos': video_list,
                    'count': len(video_list)
                })
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"List videos failed: {str(e)}", exc_info=True)
            self.set_status(500)
            self.write({'error': str(e)})

class VideoDetailHandler(BaseHandler):
    async def get(self, video_id):
        """Get details of a specific video"""
        try:
            logger.info(f"=== Video Detail Request for ID: {video_id} ===")
            db = get_db()
            try:
                video = db.query(Video).filter(Video.id == int(video_id)).first()
                
                if not video:
                    logger.warning(f"Video {video_id} not found")
                    self.set_status(404)
                    self.write({'error': 'Video not found'})
                    return
                
                logger.info(f"Returning video: {video.name}")
                self.set_status(200)
                self.write({'video': video.to_dict()})
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Get video detail failed: {str(e)}", exc_info=True)
            self.set_status(500)
            self.write({'error': str(e)})
