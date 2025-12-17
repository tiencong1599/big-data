import tornado.web
import tornado.websocket
import tornado.httpclient
import json
import asyncio
import base64
from models.video import get_db, Video
from config.settings import ALLOWED_ORIGINS, AIRFLOW_API_URL, AIRFLOW_USERNAME, AIRFLOW_PASSWORD

# Store active WebSocket connections
active_connections = {}

# Global registry of client subscriptions
# Structure: { 'processed_frame_1': [ws_conn1, ws_conn2], 'processed_frame_2': [...] }
client_subscriptions = {}

class StreamHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        # Allow all origins during development
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "*")
        self.set_header("Access-Control-Max-Age", "0")
    
    def options(self, *args, **kwargs):
        self.set_status(204)
        self.finish()
    
    async def post(self):
        """Start video streaming by triggering Airflow DAG"""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.info("=== Stream Start Request ===")
            data = json.loads(self.request.body)
            video_id = data.get('video_id')
            
            if not video_id:
                logger.warning("No video_id provided")
                self.set_status(400)
                self.write({'error': 'video_id is required'})
                return
            
            logger.info(f"Starting stream for video_id: {video_id}")
            
            # Verify video exists
            db = get_db()
            try:
                video = db.query(Video).filter(Video.id == video_id).first()
                if not video:
                    logger.warning(f"Video {video_id} not found")
                    self.set_status(404)
                    self.write({'error': 'Video not found'})
                    return
                logger.info(f"Video found: {video.name}, path: {video.file_path}")
            finally:
                db.close()
            
            # Trigger Airflow DAG
            dag_id = 'video_streaming_pipeline'
            airflow_url = f"{AIRFLOW_API_URL}/dags/{dag_id}/dagRuns"
            
            # Trigger Airflow DAG with video_id
            dag_run_data = {
                "conf": {
                    "video_id": video_id,
                    "video_path": video.file_path,
                    "roi": video.roi,
                    "homography_matrix": video.homography_matrix,
                    "fps": video.fps
                }
            }
            
            try:
                # Create Basic Auth header
                credentials = f"{AIRFLOW_USERNAME}:{AIRFLOW_PASSWORD}"
                auth_header = base64.b64encode(credentials.encode()).decode()
                
                logger.info(f"Sending request to Airflow: {airflow_url}")
                logger.info(f"Auth username: {AIRFLOW_USERNAME}")
                logger.info(f"DAG run data: {dag_run_data}")
                
                # Use Tornado's async HTTP client with timeout
                http_client = tornado.httpclient.AsyncHTTPClient()
                request = tornado.httpclient.HTTPRequest(
                    url=airflow_url,
                    method='POST',
                    headers={
                        'Content-Type': 'application/json',
                        'Authorization': f'Basic {auth_header}'
                    },
                    body=json.dumps(dag_run_data),
                    request_timeout=120.0,  # 2 minute timeout for Airflow request
                    connect_timeout=30.0     # 30 second connection timeout
                )
                
                response = await http_client.fetch(request, raise_error=False)
                
                logger.info(f"Airflow response code: {response.code}")
                logger.info(f"Airflow response body: {response.body.decode()}")
                
                if response.code in [200, 201]:
                    self.write({
                        'message': 'Video streaming started',
                        'video_id': video_id,
                        'dag_run': json.loads(response.body)
                    })
                else:
                    logger.error(f"Airflow returned error {response.code}: {response.body.decode()}")
                    self.set_status(response.code)
                    self.write({
                        'error': 'Failed to trigger Airflow DAG',
                        'details': response.body.decode()
                    })
            except Exception as e:
                logger.error(f"Exception calling Airflow: {str(e)}", exc_info=True)
                self.set_status(500)
                self.write({
                    'error': 'Could not connect to Airflow',
                    'details': str(e)
                })
                
        except Exception as e:
            logger.error(f"Stream start failed: {str(e)}", exc_info=True)
            self.set_status(500)
            self.write({'error': str(e)})

class WebSocketHandler(tornado.websocket.WebSocketHandler):
    def check_origin(self, origin):
        """Allow WebSocket connections from allowed origins"""
        return origin in ALLOWED_ORIGINS or "*" in ALLOWED_ORIGINS
    
    def open(self):
        """Called when WebSocket connection is opened"""
        video_id = self.get_argument('video_id', None)
        if video_id:
            self.video_id = video_id
            if video_id not in active_connections:
                active_connections[video_id] = []
            active_connections[video_id].append(self)
            print(f"WebSocket opened for video {video_id}")
    
    def on_message(self, message):
        """Handle incoming WebSocket messages"""
        try:
            data = json.loads(message)
            # Handle any client messages if needed
            print(f"Received message: {data}")
        except Exception as e:
            print(f"Error processing message: {e}")
    
    def on_close(self):
        """Called when WebSocket connection is closed"""
        if hasattr(self, 'video_id'):
            if self.video_id in active_connections:
                active_connections[self.video_id].remove(self)
                if not active_connections[self.video_id]:
                    del active_connections[self.video_id]
            print(f"WebSocket closed for video {self.video_id}")
    
    @classmethod
    def send_frame_to_clients(cls, video_id, frame_data):
        """Send processed frame to all connected clients for this video"""
        if video_id in active_connections:
            for connection in active_connections[video_id]:
                try:
                    connection.write_message(json.dumps({
                        'type': 'frame',
                        'data': frame_data
                    }))
                except Exception as e:
                    print(f"Error sending frame to client: {e}")

class BroadcastHandler(tornado.web.RequestHandler):
    """Endpoint for Kafka consumer to forward processed frames"""
    
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "*")
    
    def options(self, *args, **kwargs):
        self.set_status(204)
        self.finish()
    
    def post(self):
        """Receive processed frame from Kafka consumer and broadcast to WebSocket clients"""
        try:
            frame_data = json.loads(self.request.body)
            video_id = str(frame_data.get('video_id'))
            
            if not video_id:
                self.set_status(400)
                self.write({'error': 'video_id is required'})
                return
            
            # Broadcast to WebSocket clients
            WebSocketHandler.send_frame_to_clients(video_id, frame_data)
            
            self.write({'status': 'ok'})
            
        except Exception as e:
            print(f"Error in broadcast handler: {e}")
            self.set_status(500)
            self.write({'error': str(e)})

class BackendProcessedFrameHandler(tornado.websocket.WebSocketHandler):
    """
    Unified WebSocket handler that receives ALL processed frames from Kafka consumer
    This is the SINGLE entry point for all processed video data
    """
    
    def check_origin(self, origin):
        return True
    
    def open(self):
        """Called when Kafka consumer connects"""
        print("Backend processed frame channel opened (Kafka consumer connected)")
        self.is_consumer = True
    
    def on_message(self, message):
        """
        Receives processed frames from Kafka consumer
        Routes them to specific client channels based on video_id
        """
        try:
            data = json.loads(message)
            
            if data.get('type') == 'processed_frame':
                frame_data = data['data']
                video_id = frame_data['video_id']
                
                # Route to specific client channel
                channel_name = f"processed_frame_{video_id}"
                
                print(f"Routing frame {frame_data['frame_number']} to channel: {channel_name}")
                
                # Broadcast to all clients subscribed to this channel
                if channel_name in client_subscriptions:
                    for client_ws in client_subscriptions[channel_name]:
                        try:
                            client_ws.write_message(json.dumps({
                                'type': 'frame',
                                'data': frame_data
                            }))
                        except Exception as e:
                            print(f"Error sending to client: {e}")
                else:
                    print(f"No clients subscribed to {channel_name}")
        
        except Exception as e:
            print(f"Error processing backend frame: {e}")
    
    def on_close(self):
        print("Backend processed frame channel closed")


class ClientFrameHandler(tornado.websocket.WebSocketHandler):
    """
    WebSocket handler for individual client connections
    Each client subscribes to a specific channel: processed_frame_<video_id>
    """
    
    def check_origin(self, origin):
        return origin in ALLOWED_ORIGINS or "*" in ALLOWED_ORIGINS
    
    def open(self):
        """Called when frontend client connects"""
        # Get video_id from query parameter
        video_id = self.get_argument('video_id', None)
        
        if not video_id:
            self.close(1000, "video_id is required")
            return
        
        self.video_id = video_id
        self.channel_name = f"processed_frame_{video_id}"
        
        # Register this connection to the channel
        if self.channel_name not in client_subscriptions:
            client_subscriptions[self.channel_name] = []
        
        client_subscriptions[self.channel_name].append(self)
        
        print(f"Client subscribed to channel: {self.channel_name}")
        
        # Send placeholder frame immediately
        self.write_message(json.dumps({
            'type': 'placeholder',
            'data': {
                'video_id': int(video_id),
                'frame_number': 0,
                'processed_frame': self.get_placeholder_frame(),
                'message': 'Waiting for stream to start...'
            }
        }))
    
    def on_message(self, message):
        """Handle client messages (e.g., ping/pong)"""
        pass
    
    def on_close(self):
        """Remove this connection from subscriptions"""
        if hasattr(self, 'channel_name') and self.channel_name in client_subscriptions:
            client_subscriptions[self.channel_name].remove(self)
            if not client_subscriptions[self.channel_name]:
                del client_subscriptions[self.channel_name]
            print(f"Client unsubscribed from channel: {self.channel_name}")
    
    def get_placeholder_frame(self):
        """Generate base64 placeholder image"""
        import cv2
        import numpy as np
        
        # Create blank frame with text
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(frame, "Waiting for stream...", (150, 240), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        _, buffer = cv2.imencode('.jpg', frame)
        return base64.b64encode(buffer).decode('utf-8')


# Update app routes
class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            # ... existing routes ...
            
            # NEW: Unified backend channel (for Kafka consumer)
            (r"/ws/backend_processed_frame", BackendProcessedFrameHandler),
            
            # NEW: Client channel (for frontend)
            (r"/ws/client/stream", ClientFrameHandler),
        ]
        
        super(Application, self).__init__(handlers, **settings)
