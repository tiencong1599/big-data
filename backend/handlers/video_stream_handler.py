import tornado.web
import tornado.gen
import cv2
import asyncio
import os
import logging
from models.video import get_db, Video
from config.settings import ALLOWED_ORIGINS

logger = logging.getLogger(__name__)

class VideoStreamHandler(tornado.web.RequestHandler):
    """
    MJPEG (Motion JPEG) video streaming handler
    
    Serves raw video frames as MJPEG stream for client-side rendering
    URL: /api/video/stream/<video_id>
    
    MJPEG format:
    - Content-Type: multipart/x-mixed-replace; boundary=frame
    - Each frame prefixed with boundary marker
    - Frames encoded as JPEG with boundary headers
    """
    
    def set_default_headers(self):
        """Set CORS headers"""
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "*")
        self.set_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.set_header("Pragma", "no-cache")
        self.set_header("Expires", "0")
    
    def options(self, video_id):
        """Handle preflight"""
        self.set_status(204)
        self.finish()
    
    @tornado.gen.coroutine
    def get(self, video_id):
        """
        Stream video frames as MJPEG
        
        Args:
            video_id (str): Video ID from URL
        """
        try:
            video_id = int(video_id)
            logger.info(f"[MJPEG-STREAM] Starting stream for video {video_id}")
            
            # Get video from database
            db = get_db()
            try:
                video = db.query(Video).filter(Video.id == video_id).first()
                if not video:
                    logger.warning(f"[MJPEG-STREAM] Video {video_id} not found")
                    self.set_status(404)
                    self.write({'error': 'Video not found'})
                    return
                
                video_path = video.file_path
                logger.info(f"[MJPEG-STREAM] Video path: {video_path}")
                
                if not os.path.exists(video_path):
                    logger.error(f"[MJPEG-STREAM] File not found: {video_path}")
                    self.set_status(404)
                    self.write({'error': 'Video file not found'})
                    return
                    
            finally:
                db.close()
            
            # Set MJPEG headers
            self.set_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            
            # Open video capture
            cap = cv2.VideoCapture(video_path)
            
            if not cap.isOpened():
                logger.error(f"[MJPEG-STREAM] Could not open video: {video_path}")
                self.set_status(500)
                self.write({'error': 'Could not open video file'})
                return
            
            # Get video properties
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            frame_delay = 1.0 / fps  # Delay between frames in seconds
            
            logger.info(f"[MJPEG-STREAM] Streaming at {fps} FPS (delay={frame_delay:.3f}s)")
            
            frame_count = 0
            
            try:
                while True:
                    ret, frame = cap.read()
                    
                    if not ret:
                        logger.info(f"[MJPEG-STREAM] End of video reached (frame {frame_count})")
                        break
                    
                    # Encode frame as JPEG
                    _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    frame_bytes = jpeg.tobytes()
                    
                    # Write MJPEG frame with boundary
                    try:
                        self.write(b'--frame\r\n')
                        self.write(b'Content-Type: image/jpeg\r\n')
                        self.write(f'Content-Length: {len(frame_bytes)}\r\n\r\n'.encode())
                        self.write(frame_bytes)
                        self.write(b'\r\n')
                        
                        # Flush immediately
                        yield self.flush()
                        
                    except tornado.iostream.StreamClosedError:
                        logger.info(f"[MJPEG-STREAM] Client disconnected at frame {frame_count}")
                        break
                    
                    frame_count += 1
                    
                    # Log progress every 100 frames
                    if frame_count % 100 == 0:
                        logger.debug(f"[MJPEG-STREAM] Streamed frame {frame_count}")
                    
                    # Throttle to match video FPS (prevent sending too fast)
                    yield tornado.gen.sleep(frame_delay)
                    
            finally:
                cap.release()
                logger.info(f"[MJPEG-STREAM] Stream ended for video {video_id}, total frames: {frame_count}")
                
        except Exception as e:
            logger.error(f"[MJPEG-STREAM] Stream error: {str(e)}", exc_info=True)
            if not self._finished:
                self.set_status(500)
                self.write({'error': str(e)})
