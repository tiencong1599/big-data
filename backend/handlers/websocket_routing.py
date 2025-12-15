# backend/handlers/websocket_routing.py

import tornado.web
import tornado.websocket
import json
import base64
import cv2
import numpy as np
from typing import Dict, List, Set
from config.settings import ALLOWED_ORIGINS

# ============================================================================
# GLOBAL STATE MANAGEMENT
# ============================================================================

# Structure: { 'processed_frame_1': [ws_conn1, ws_conn2], 'processed_frame_2': [...] }
client_subscriptions: Dict[str, List[tornado.websocket.WebSocketHandler]] = {}

# Track active streams
active_streams: Set[int] = set()


# ============================================================================
# BACKEND CHANNEL HANDLER (Kafka Consumer → Backend)
# ============================================================================

class BackendProcessedFrameHandler(tornado.websocket.WebSocketHandler):
    """
    Single unified WebSocket endpoint for Kafka consumer
    Receives ALL processed frames and routes them internally
    
    URL: ws://backend:8686/ws/backend_processed_frame
    """
    
    def check_origin(self, origin):
        """Allow connections from Kafka consumer service"""
        return True
    
    def open(self):
        """Kafka consumer establishes connection"""
        print("[BACKEND-CHANNEL] Kafka consumer connected to unified channel")
        self.is_consumer = True
    
    def on_message(self, message):
        """
        Receives processed frames from Kafka consumer
        Routes to appropriate client channels based on video_id
        
        Message Format:
        {
            "type": "processed_frame",
            "data": {
                "video_id": 1,
                "frame_number": 42,
                "processed_frame": "<base64>",
                "vehicles": [...],
                "total_vehicles": 3,
                ...
            }
        }
        """
        try:
            data = json.loads(message)
            
            if data.get('type') == 'processed_frame':
                frame_data = data['data']
                video_id = frame_data.get('video_id')
                frame_number = frame_data.get('frame_number')
                
                if not video_id:
                    print(f"[BACKEND-CHANNEL] Error: No video_id in frame data")
                    return
                
                # Determine target channel
                channel_name = f"processed_frame_{video_id}"
                
                print(f"[BACKEND-CHANNEL] Routing frame {frame_number} to channel '{channel_name}'")
                
                # Get subscribed clients
                if channel_name in client_subscriptions:
                    clients = client_subscriptions[channel_name]
                    print(f"[BACKEND-CHANNEL] Broadcasting to {len(clients)} client(s)")
                    
                    # Broadcast to all subscribed clients
                    dead_clients = []
                    for client_ws in clients:
                        try:
                            message_to_send = {
                                'type': 'frame',
                                'data': frame_data
                            }
                            message_json = json.dumps(message_to_send)
                            print(f"[BACKEND-CHANNEL] Sending frame {frame_number}: type={message_to_send['type']}, data_keys={list(frame_data.keys())}")
                            client_ws.write_message(message_json)
                        except Exception as e:
                            print(f"[BACKEND-CHANNEL] Error sending to client: {e}")
                            import traceback
                            traceback.print_exc()
                            dead_clients.append(client_ws)
                    
                    # Remove dead connections
                    for dead_client in dead_clients:
                        clients.remove(dead_client)
                    
                else:
                    print(f"[BACKEND-CHANNEL] Warning: No clients subscribed to '{channel_name}'")
                
                # Handle end-of-stream
                if frame_data.get('end_of_stream'):
                    print(f"[BACKEND-CHANNEL] Stream {video_id} ended")
                    active_streams.discard(video_id)
            
            elif data.get('type') == 'heartbeat':
                # Respond to heartbeat from consumer
                self.write_message(json.dumps({'type': 'heartbeat_ack'}))
        
        except Exception as e:
            print(f"[BACKEND-CHANNEL] Error processing message: {e}")
            import traceback
            traceback.print_exc()
    
    def on_close(self):
        """Kafka consumer disconnected"""
        print("[BACKEND-CHANNEL] Kafka consumer disconnected from unified channel")


# ============================================================================
# CLIENT CHANNEL HANDLER (Frontend → Backend)
# ============================================================================

class ClientFrameHandler(tornado.websocket.WebSocketHandler):
    """
    Individual client WebSocket connections
    Each client subscribes to a specific channel: processed_frame_<video_id>
    
    URL: ws://backend:8686/ws/client/stream?video_id=1
    """
    
    def check_origin(self, origin):
        """Allow connections from frontend"""
        return True
    
    def open(self):
        """
        Frontend client connects and subscribes to specific video channel
        """
        # Extract video_id from query parameter
        video_id = self.get_argument('video_id', None)
        
        if not video_id:
            print("[CLIENT-CHANNEL] Error: Missing video_id parameter")
            self.close(1008, "video_id is required")
            return
        
        try:
            self.video_id = int(video_id)
            self.channel_name = f"processed_frame_{self.video_id}"
            
            # Register this connection to the channel
            if self.channel_name not in client_subscriptions:
                client_subscriptions[self.channel_name] = []
            
            client_subscriptions[self.channel_name].append(self)
            
            print(f"[CLIENT-CHANNEL] Client subscribed to '{self.channel_name}'")
            print(f"[CLIENT-CHANNEL] Total subscribers on '{self.channel_name}': {len(client_subscriptions[self.channel_name])}")
            
            # Send placeholder frame immediately
            placeholder_data = {
                'video_id': self.video_id,
                'frame_number': 0,
                'processed_frame': self._generate_placeholder_frame(),
                'message': 'Waiting for stream to start...',
                'vehicles': [],
                'total_vehicles': 0
            }
            
            self.write_message(json.dumps({
                'type': 'placeholder',
                'data': placeholder_data
            }))
            
            print(f"[CLIENT-CHANNEL] Sent placeholder frame to client for video {self.video_id}")
        
        except ValueError:
            print(f"[CLIENT-CHANNEL] Error: Invalid video_id '{video_id}'")
            self.close(1008, "Invalid video_id")
    
    def on_message(self, message):
        """
        Handle messages from client (e.g., ping/pong, commands)
        """
        try:
            data = json.loads(message)
            
            if data.get('type') == 'ping':
                # Respond to ping
                self.write_message(json.dumps({'type': 'pong'}))
            
            elif data.get('type') == 'status_request':
                # Send stream status
                is_active = self.video_id in active_streams
                self.write_message(json.dumps({
                    'type': 'status_response',
                    'data': {
                        'video_id': self.video_id,
                        'is_streaming': is_active
                    }
                }))
        
        except Exception as e:
            print(f"[CLIENT-CHANNEL] Error processing client message: {e}")
    
    def on_close(self):
        """
        Remove this connection from subscriptions when client disconnects
        """
        if hasattr(self, 'channel_name') and self.channel_name in client_subscriptions:
            try:
                client_subscriptions[self.channel_name].remove(self)
                remaining = len(client_subscriptions[self.channel_name])
                
                print(f"[CLIENT-CHANNEL] Client unsubscribed from '{self.channel_name}'")
                print(f"[CLIENT-CHANNEL] Remaining subscribers on '{self.channel_name}': {remaining}")
                
                # Clean up empty channel
                if remaining == 0:
                    del client_subscriptions[self.channel_name]
                    print(f"[CLIENT-CHANNEL] Channel '{self.channel_name}' deleted (no subscribers)")
            
            except ValueError:
                # Connection already removed
                pass
    
    def _generate_placeholder_frame(self) -> str:
        """
        Generate a base64-encoded placeholder image
        Shows "Waiting for stream..." message
        """
        # Create blank frame (640x480, black background)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Add text
        text = "Waiting for stream to start..."
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.8
        thickness = 2
        color = (255, 255, 255)  # White
        
        # Get text size for centering
        text_size = cv2.getTextSize(text, font, font_scale, thickness)[0]
        text_x = (frame.shape[1] - text_size[0]) // 2
        text_y = (frame.shape[0] + text_size[1]) // 2
        
        cv2.putText(frame, text, (text_x, text_y), font, font_scale, color, thickness)
        
        # Add video ID info
        info_text = f"Video ID: {self.video_id}"
        cv2.putText(frame, info_text, (20, 40), font, 0.6, (180, 180, 180), 1)
        
        # Encode to JPEG
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        
        # Convert to base64
        return base64.b64encode(buffer).decode('utf-8')


# ============================================================================
# MANAGEMENT ENDPOINTS (Optional)
# ============================================================================

class WebSocketStatusHandler(tornado.web.RequestHandler):
    """
    HTTP endpoint to check WebSocket connection status
    GET /api/websocket/status
    """
    
    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header("Content-Type", "application/json")
    
    def get(self):
        """Return current WebSocket subscription status"""
        status = {
            'channels': {},
            'total_clients': 0,
            'active_streams': list(active_streams)
        }
        
        for channel_name, clients in client_subscriptions.items():
            status['channels'][channel_name] = {
                'subscriber_count': len(clients),
                'video_id': int(channel_name.replace('processed_frame_', ''))
            }
            status['total_clients'] += len(clients)
        
        self.write(status)


# ============================================================================
# APPLICATION REGISTRATION
# ============================================================================

def get_websocket_handlers():
    """
    Returns list of WebSocket handlers for registration in main app
    """
    return [
        # Backend unified channel (for Kafka consumer)
        (r"/ws/backend_processed_frame", BackendProcessedFrameHandler),
        
        # Client channels (for frontend)
        (r"/ws/client/stream", ClientFrameHandler),
        
        # Status endpoint
        (r"/api/websocket/status", WebSocketStatusHandler),
    ]