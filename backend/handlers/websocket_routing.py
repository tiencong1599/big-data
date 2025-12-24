# backend/handlers/websocket_routing.py

import tornado.web
import tornado.websocket
import json
import base64
import cv2
import numpy as np
import redis
import os
from typing import Dict, List, Set
from config.settings import ALLOWED_ORIGINS
from handlers.analytics_persistence import get_persistence_handler

# ============================================================================
# GLOBAL STATE MANAGEMENT
# ============================================================================

# Structure: { 'processed_frame_1': [ws_conn1, ws_conn2], 'processed_frame_2': [...] }
client_subscriptions: Dict[str, Set[tornado.websocket.WebSocketHandler]] = {}

# Track active streams
active_streams: Set[int] = set()

# Redis client for subscription cache management
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
redis_cache_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=0,
    decode_responses=True,
    socket_keepalive=True,
    socket_connect_timeout=5
)

SUBSCRIPTION_CACHE_PREFIX = 'websocket:subscription:video:'
ANALYTICS_CACHE_PREFIX = 'websocket:analytics:video:'
SUBSCRIPTION_CACHE_TTL = 3600  # 1 hour TTL for safety


# ============================================================================
# BACKEND CHANNEL HANDLER (Kafka Consumer → Backend)
# ============================================================================

class BackendProcessedFrameHandler(tornado.websocket.WebSocketHandler):
    """
    Single unified WebSocket endpoint for Redis consumer
    Receives ALL processed frames and routes them internally
    """
    
    def check_origin(self, origin):
        return True
    
    def open(self):
        print("[BACKEND-CHANNEL] ✓ Redis consumer connected")
    
    def on_message(self, message):
        """
        Receives processed frames from Redis consumer
        Routes to appropriate client channels based on video_id
        """
        try:
            data = json.loads(message)
            
            if data.get('type') == 'processed_frame':
                frame_data = data['data']
                video_id = frame_data.get('video_id')
                frame_number = frame_data.get('frame_number')
                
                if not video_id:
                    print(f"[BACKEND-CHANNEL] ❌ Error: No video_id in frame data")
                    return
                
                # Determine target channel
                channel_name = f"processed_frame_{video_id}"
                
                # Check if anyone is subscribed (most frames filtered by redis_consumer)
                if channel_name not in client_subscriptions or len(client_subscriptions[channel_name]) == 0:
                    # This should rarely happen now that redis_consumer pre-filters
                    return
                
                # Get subscribed clients
                clients = client_subscriptions[channel_name]
                print(f"[BACKEND-CHANNEL] ✓ Broadcasting frame {frame_number} to {len(clients)} client(s)")
                
                # Broadcast to all subscribed clients
                dead_clients = set()
                for client_ws in clients:
                    try:
                        message_to_send = {
                            'type': 'frame',
                            'data': frame_data
                        }
                        message_json = json.dumps(message_to_send)
                        client_ws.write_message(message_json)
                        print(f"[BACKEND-CHANNEL] ✓ Sent frame {frame_number} to client")
                    except Exception as e:
                        print(f"[BACKEND-CHANNEL] ❌ Error sending to client: {e}")
                        dead_clients.add(client_ws)
                
                # Remove dead connections
                for dead_client in dead_clients:
                    clients.discard(dead_client)
                
                # Handle end-of-stream
                if frame_data.get('end_of_stream'):
                    print(f"[BACKEND-CHANNEL] Stream {video_id} ended")
                    active_streams.discard(video_id)
            
            elif data.get('type') == 'heartbeat':
                self.write_message(json.dumps({'type': 'heartbeat_ack'}))
        
        except Exception as e:
            print(f"[BACKEND-CHANNEL] ❌ Error processing message: {e}")
            import traceback
            traceback.print_exc()
    
    def on_close(self):
        print("[BACKEND-CHANNEL] Redis consumer disconnected")


class BackendAnalyticsHandler(tornado.websocket.WebSocketHandler):
    """
    WebSocket endpoint for analytics data (stats + speeding vehicles)
    Receives analytics from Redis consumer and routes to analytics channels
    """
    
    def check_origin(self, origin):
        return True
    
    def open(self):
        print("[BACKEND-ANALYTICS-CHANNEL] ✓ Redis consumer connected")
    
    def on_message(self, message):
        """
        Receives analytics data from Redis consumer
        Routes to appropriate analytics_metrics_<video_id> channels
        Phase 3: Also persists to database asynchronously
        """
        try:
            data = json.loads(message)
            
            if data.get('type') == 'analytics_update':
                analytics_data = data['data']
                video_id = analytics_data.get('video_id')
                frame_number = analytics_data.get('frame_number')
                
                if not video_id:
                    print(f"[BACKEND-ANALYTICS-CHANNEL] ❌ Error: No video_id in analytics data")
                    return
                
                # Phase 3: Persist analytics data asynchronously (non-blocking)
                persistence_handler = get_persistence_handler()
                tornado.ioloop.IOLoop.current().spawn_callback(
                    persistence_handler.persist_analytics_snapshot,
                    analytics_data
                )
                
                # Determine target analytics channel
                channel_name = f"analytics_metrics_{video_id}"
                
                # Check if anyone is subscribed
                if channel_name not in client_subscriptions or len(client_subscriptions[channel_name]) == 0:
                    return
                
                # Get subscribed clients
                clients = client_subscriptions[channel_name]
                speeding_count = len(analytics_data.get('speeding_vehicles', []))
                print(f"[BACKEND-ANALYTICS-CHANNEL] ✓ Broadcasting analytics (frame {frame_number}, speeding: {speeding_count}) to {len(clients)} client(s)")
                
                # Broadcast to all subscribed clients
                dead_clients = set()
                for client_ws in clients:
                    try:
                        message_to_send = {
                            'type': 'analytics',
                            'data': analytics_data
                        }
                        message_json = json.dumps(message_to_send)
                        client_ws.write_message(message_json)
                    except Exception as e:
                        print(f"[BACKEND-ANALYTICS-CHANNEL] ❌ Error sending to client: {e}")
                        dead_clients.add(client_ws)
                
                # Remove dead connections
                for dead_client in dead_clients:
                    clients.discard(dead_client)
            
            elif data.get('type') == 'heartbeat':
                self.write_message(json.dumps({'type': 'heartbeat_ack'}))
        
        except Exception as e:
            print(f"[BACKEND-ANALYTICS-CHANNEL] ❌ Error processing message: {e}")
            import traceback
            traceback.print_exc()
    
    def on_close(self):
        print("[BACKEND-ANALYTICS-CHANNEL] Redis consumer disconnected")


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
        from config.settings import ALLOWED_ORIGINS
        is_allowed = origin in ALLOWED_ORIGINS or "*" in ALLOWED_ORIGINS
        
        if not is_allowed:
            print(f"[CLIENT-CHANNEL] ❌ REJECTED connection from origin: {origin}")
        else:
            print(f"[CLIENT-CHANNEL] ✅ ACCEPTED connection from origin: {origin}")
        
        return is_allowed
    
    def open(self):
        """Frontend client connects"""
        print(f"[CLIENT-CHANNEL] ✓ Client connected (waiting for subscription message)")
        print(f"[CLIENT-CHANNEL] 📊 Current subscriptions before: {list(client_subscriptions.keys())}")
    
    def on_message(self, message):
        """Handle subscription requests"""
        print(f"[CLIENT-CHANNEL] 📨 RAW message received: {message}")
        
        try:
            data = json.loads(message)
            action = data.get('action')
            channel = data.get('channel')
            
            print(f"[CLIENT-CHANNEL] 📨 Parsed message: action={action}, channel={channel}")
            
            if action == 'subscribe':
                if channel not in client_subscriptions:
                    client_subscriptions[channel] = set()
                    print(f"[CLIENT-CHANNEL] ➕ Created new channel: {channel}")
                
                client_subscriptions[channel].add(self)
                print(f"[CLIENT-CHANNEL] ✅ Client subscribed to '{channel}' | Total subscribers: {len(client_subscriptions[channel])}")
                print(f"[CLIENT-CHANNEL] 📊 All active channels: {list(client_subscriptions.keys())}")
                
                # Write to Redis cache: video_id -> "true"
                try:
                    # Determine if this is a frame or analytics channel
                    if channel.startswith('processed_frame_'):
                        video_id = channel.replace('processed_frame_', '')
                        cache_key = f"{SUBSCRIPTION_CACHE_PREFIX}{video_id}"
                        redis_cache_client.setex(cache_key, SUBSCRIPTION_CACHE_TTL, 'true')
                        print(f"[CLIENT-CHANNEL] 💾 Frame cache set: {cache_key} = true")
                    elif channel.startswith('analytics_metrics_'):
                        video_id = channel.replace('analytics_metrics_', '')
                        cache_key = f"{ANALYTICS_CACHE_PREFIX}{video_id}"
                        redis_cache_client.setex(cache_key, SUBSCRIPTION_CACHE_TTL, 'true')
                        print(f"[CLIENT-CHANNEL] 💾 Analytics cache set: {cache_key} = true")
                except Exception as e:
                    print(f"[CLIENT-CHANNEL] ⚠️ Failed to set Redis cache: {e}")
                
                # Send acknowledgment
                self.write_message(json.dumps({
                    'type': 'subscription_ack',
                    'channel': channel,
                    'status': 'subscribed'
                }))
            
            elif action == 'unsubscribe':
                if channel in client_subscriptions:
                    client_subscriptions[channel].discard(self)
                    print(f"[CLIENT-CHANNEL] ➖ Client unsubscribed from '{channel}' | Remaining: {len(client_subscriptions[channel])}")
                    
                    if len(client_subscriptions[channel]) == 0:
                        del client_subscriptions[channel]
                        print(f"[CLIENT-CHANNEL] 🗑️ Channel '{channel}' removed (no subscribers)")
                        
                        # Clear appropriate Redis cache when no subscribers left
                        try:
                            if channel.startswith('processed_frame_'):
                                video_id = channel.replace('processed_frame_', '')
                                cache_key = f"{SUBSCRIPTION_CACHE_PREFIX}{video_id}"
                            elif channel.startswith('analytics_metrics_'):
                                video_id = channel.replace('analytics_metrics_', '')
                                cache_key = f"{ANALYTICS_CACHE_PREFIX}{video_id}"
                            else:
                                return
                            
                            redis_cache_client.delete(cache_key)
                            print(f"[CLIENT-CHANNEL] 🗑️ Redis cache cleared: {cache_key}")
                        except Exception as e:
                            print(f"[CLIENT-CHANNEL] ⚠️ Failed to clear Redis cache: {e}")
        
        except json.JSONDecodeError as e:
            print(f"[CLIENT-CHANNEL] ❌ JSON parse error: {e}")
            print(f"[CLIENT-CHANNEL] Raw message was: {message}")
        except Exception as e:
            print(f"[CLIENT-CHANNEL] ❌ Error processing message: {e}")
            import traceback
            traceback.print_exc()
    
    def on_close(self):
        """Remove this connection from subscriptions when client disconnects"""
        for channel in list(client_subscriptions.keys()):
            if self in client_subscriptions[channel]:
                client_subscriptions[channel].discard(self)
                print(f"[CLIENT-CHANNEL] Client disconnected from '{channel}'")
                
                if len(client_subscriptions[channel]) == 0:
                    del client_subscriptions[channel]
                    
                    # Clear appropriate Redis cache when last client disconnects
                    try:
                        if channel.startswith('processed_frame_'):
                            video_id = channel.replace('processed_frame_', '')
                            cache_key = f"{SUBSCRIPTION_CACHE_PREFIX}{video_id}"
                        elif channel.startswith('analytics_metrics_'):
                            video_id = channel.replace('analytics_metrics_', '')
                            cache_key = f"{ANALYTICS_CACHE_PREFIX}{video_id}"
                        else:
                            continue
                        
                        redis_cache_client.delete(cache_key)
                        print(f"[CLIENT-CHANNEL] 🗑️ Redis cache cleared on disconnect: {cache_key}")
                    except Exception as e:
                        print(f"[CLIENT-CHANNEL] ⚠️ Failed to clear Redis cache on disconnect: {e}")
        
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
            # Extract video_id from channel name (processed_frame_X or analytics_metrics_X)
            video_id = None
            if 'processed_frame_' in channel_name:
                video_id = int(channel_name.replace('processed_frame_', ''))
            elif 'analytics_metrics_' in channel_name:
                video_id = int(channel_name.replace('analytics_metrics_', ''))
            
            status['channels'][channel_name] = {
                'subscriber_count': len(clients),
                'video_id': video_id,
                'type': 'frame' if 'processed_frame_' in channel_name else 'analytics'
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
        # Backend channels (for Redis consumer)
        (r"/ws/backend/processed", BackendProcessedFrameHandler),
        (r"/ws/backend/analytics", BackendAnalyticsHandler),
        
        # Client channels (for frontend)
        (r"/ws/client/stream", ClientFrameHandler),

        # Status endpoint
        (r"/api/websocket/status", WebSocketStatusHandler),
    ]