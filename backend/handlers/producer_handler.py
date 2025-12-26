import tornado.web
import json
import logging
from services.redis_producer import VideoFrameProducer

logger = logging.getLogger(__name__)

class ProducerHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "*")
        self.set_header("Access-Control-Max-Age", "0")
    
    def options(self, *args, **kwargs):
        self.set_status(204)
        self.finish()
    
    async def post(self):
        """Stream video frames to Kafka"""
        try:
            logger.info("=== Producer Stream Request ===")
            data = json.loads(self.request.body)
            video_id = data.get('video_id')
            video_path = data.get('video_path')
            
            if not video_id or not video_path:
                logger.warning("Missing video_id or video_path")
                self.set_status(400)
                self.write({'error': 'video_id and video_path are required'})
                return
            
            logger.info(f"Starting Kafka producer for video_id: {video_id}, path: {video_path}")
            
            # Create producer and stream video
            producer = VideoFrameProducer()
            
            try:
                # Stream video to Redis (this is a blocking operation)
                total_frames = producer.stream_video(video_id, video_path)
                
                logger.info(f"Finished streaming video {video_id}, total frames: {total_frames}")
                self.write({
                    'message': 'Video streaming completed',
                    'video_id': video_id,
                    'total_frames': total_frames
                })
                
            except Exception as e:
                logger.error(f"Error streaming video: {str(e)}", exc_info=True)
                self.set_status(500)
                self.write({
                    'error': 'Failed to stream video',
                    'details': str(e)
                })
            finally:
                producer.close()
                
        except Exception as e:
            logger.error(f"Producer request failed: {str(e)}", exc_info=True)
            self.set_status(500)
            self.write({'error': str(e)})
