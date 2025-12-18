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
client_subscriptions: Dict[str, Set[tornado.websocket.WebSocketHandler]] = {}

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
                
                # CRITICAL OPTIMIZATION: Check if anyone is subscribed
                if channel_name not in client_subscriptions or len(client_subscriptions[channel_name]) == 0:
                    # NO SUBSCRIBERS - SKIP PROCESSING
                    return
                
                # Get subscribed clients
                if channel_name in client_subscriptions:
                    clients = client_subscriptions[channel_name]
                    print(f"[BACKEND-CHANNEL] Broadcasting to {len(clients)} client(s)")
                    
                    # Broadcast to all subscribed clients
                    dead_clients = set()
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
                            dead_clients.add(client_ws)
                    
                    # Remove dead connections
                    for dead_client in dead_clients:
                        clients.discard(dead_client)
                    
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
        is_allowed = origin in ALLOWED_ORIGINS or "*" in ALLOWED_ORIGINS
        
        if not is_allowed:
            print(f"[CLIENT-CHANNEL] ❌ REJECTED connection from origin: {origin}")
        return is_allowed
    
    def open(self):
        """
        Frontend client connects and subscribes to specific video channel
        """
        print("[CLIENT-CHANNEL] Client connected")
    
    def on_message(self, message):
        """
        Handle subscription requests
        """
        try:
            data = json.loads(message)
            action = data.get('action')
            channel = data.get('channel')
            
            if action == 'subscribe':
                if channel not in client_subscriptions:
                    client_subscriptions[channel] = set()
                client_subscriptions[channel].add(self)
                print(f"[CLIENT-CHANNEL] Client subscribed to '{channel}' | Total: {len(client_subscriptions[channel])}")
            
            elif action == 'unsubscribe':
                if channel in client_subscriptions:
                    client_subscriptions[channel].discard(self)
                    print(f"[CLIENT-CHANNEL] Client unsubscribed from '{channel}' | Remaining: {len(client_subscriptions[channel])}")
                    
                    # Clean up empty channels
                    if len(client_subscriptions[channel]) == 0:
                        del client_subscriptions[channel]
                        print(f"[CLIENT-CHANNEL] Channel '{channel}' removed (no subscribers)")
        
        except Exception as e:
            print(f"[CLIENT-CHANNEL] Error processing message: {e}")
    
    def on_close(self):
        """
        Remove this connection from subscriptions when client disconnects
        """
        # Remove this client from all channels
        for channel in list(client_subscriptions.keys()):
            if self in client_subscriptions[channel]:
                client_subscriptions[channel].discard(self)
                print(f"[CLIENT-CHANNEL] Client disconnected from '{channel}'")
                
                if len(client_subscriptions[channel]) == 0:
                    del client_subscriptions[channel]
        
        print("[CLIENT-CHANNEL] Client fully disconnected")


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