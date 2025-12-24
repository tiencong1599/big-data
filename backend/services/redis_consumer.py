import redis
import json
import os
import time
import websocket

# Get settings from environment variables
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_RESULT_STREAM = os.getenv('REDIS_RESULT_STREAM', 'processed-frames')
BACKEND_URL = os.getenv('BACKEND_URL', 'http://video_streaming_backend:8686')

class ResultConsumer:
    """
    Consumer to read processed frames from Redis Streams and forward to backend WebSocket handler
    This runs as a separate service alongside the Tornado backend
    """
    
    def __init__(self):
        print(f"Initializing Redis consumer...")
        print(f"  Redis host: {REDIS_HOST}:{REDIS_PORT}")
        print(f"  Stream: {REDIS_RESULT_STREAM}")
        print(f"  Backend URL: {BACKEND_URL}")
        
        self.redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=0,
            decode_responses=True,  # Auto-decode strings
            socket_keepalive=True,
            socket_connect_timeout=5
        )
        
        # Create consumer group if it doesn't exist
        try:
            self.redis_client.xgroup_create(
                REDIS_RESULT_STREAM,
                'redis-consumer-group',
                id='0',
                mkstream=True
            )
            print("  Created consumer group 'redis-consumer-group'")
        except redis.exceptions.ResponseError as e:
            if 'BUSYGROUP' in str(e):
                print("  Consumer group already exists")
            else:
                raise
        
        # Convert HTTP URL to WebSocket URL
        ws_url = BACKEND_URL.replace('http://', 'ws://').replace('https://', 'wss://')
        self.backend_ws_frame_url = f"{ws_url}/ws/backend/processed"
        self.backend_ws_analytics_url = f"{ws_url}/ws/backend/analytics"
        self.ws_frame = None
        self.ws_analytics = None
        self.reconnect_delay = 5
        self.last_id = '>'  # Read only new messages
        
        # Subscription cache key prefixes (matches backend)
        self.subscription_cache_prefix = 'websocket:subscription:video:'
        self.analytics_cache_prefix = 'websocket:analytics:video:'
    
    def connect_to_backend(self):
        """Establish dual WebSocket connections to backend (frames + analytics)"""
        max_retries = 5
        retry_count = 0
        
        # Connect to frame channel
        while retry_count < max_retries:
            try:
                retry_count += 1
                print(f"[FRAME-WS] Attempting to connect to {self.backend_ws_frame_url}...")
                self.ws_frame = websocket.create_connection(
                    self.backend_ws_frame_url,
                    timeout=10
                )
                print("[FRAME-WS] ✓ Connected to backend frame channel")
                break
            except Exception as e:
                print(f"[FRAME-WS] ✗ Connection failed (attempt {retry_count}/{max_retries}): {e}")
                if retry_count < max_retries:
                    time.sleep(self.reconnect_delay)
        
        if not self.ws_frame:
            return False
        
        # Connect to analytics channel
        retry_count = 0
        while retry_count < max_retries:
            try:
                retry_count += 1
                print(f"[ANALYTICS-WS] Attempting to connect to {self.backend_ws_analytics_url}...")
                self.ws_analytics = websocket.create_connection(
                    self.backend_ws_analytics_url,
                    timeout=10
                )
                print("[ANALYTICS-WS] ✓ Connected to backend analytics channel\n")
                return True
            except Exception as e:
                print(f"[ANALYTICS-WS] ✗ Connection failed (attempt {retry_count}/{max_retries}): {e}")
                if retry_count < max_retries:
                    time.sleep(self.reconnect_delay)
        
        return False
    
    def has_frame_subscribers(self, video_id):
        """Check if video has any frame channel subscribers"""
        try:
            cache_key = f"{self.subscription_cache_prefix}{video_id}"
            result = self.redis_client.get(cache_key)
            return result == 'true' if result is not None else False
        except Exception as e:
            print(f"[SUBSCRIPTION-CHECK] Error checking frame cache for video {video_id}: {e}")
            return True  # Fail-safe
    
    def has_analytics_subscribers(self, video_id):
        """Check if video has any analytics channel subscribers"""
        try:
            cache_key = f"{self.analytics_cache_prefix}{video_id}"
            result = self.redis_client.get(cache_key)
            return result == 'true' if result is not None else False
        except Exception as e:
            print(f"[SUBSCRIPTION-CHECK] Error checking analytics cache for video {video_id}: {e}")
            return True  # Fail-safe
    
    def start_consuming(self):
        """Consume processed frames from Redis Streams and send to backend via WebSocket"""
        if not self.connect_to_backend():
            print("Could not establish WebSocket connection. Exiting.")
            return
        
        print(f"Starting to consume from {REDIS_RESULT_STREAM}...")
        print("Waiting for messages...\n")
        
        frame_count = 0
        error_count = 0
        
        # Use XREADGROUP for reliable, real-time consumption
        while True:
            try:
                # Read messages from stream (blocking with 1000ms timeout)
                messages = self.redis_client.xreadgroup(
                    groupname='redis-consumer-group',
                    consumername='consumer-1',
                    streams={REDIS_RESULT_STREAM: self.last_id},
                    count=1,  # Process ONE message at a time
                    block=1000  # 1 second block timeout
                )
                
                if not messages:
                    continue
                
                # Process each message immediately
                for stream_name, stream_messages in messages:
                    for message_id, message_data in stream_messages:
                        try:
                            # Parse frame data
                            video_id = message_data.get('video_id')
                            frame_number = message_data.get('frame_number', 'unknown')
                            video_id_int = int(video_id) if video_id else None
                            
                            # Check subscribers for both channels
                            has_frame_subs = video_id_int and self.has_frame_subscribers(video_id_int)
                            has_analytics_subs = video_id_int and self.has_analytics_subscribers(video_id_int)
                            
                            # Skip if no subscribers at all
                            if not has_frame_subs and not has_analytics_subs:
                                self.redis_client.xack(REDIS_RESULT_STREAM, 'redis-consumer-group', message_id)
                                continue
                            
                            # Parse common data
                            frame_number_int = int(frame_number) if frame_number.isdigit() else frame_number
                            timestamp = int(message_data.get('timestamp', 0))
                            vehicles = json.loads(message_data.get('vehicles', '[]'))
                            roi_polygon = json.loads(message_data.get('roi_polygon', '[]'))
                            
                            # Build stats from individual fields (Spark doesn't send 'stats' as JSON)
                            # Use cumulative_total_vehicles for total count (not just current frame)
                            cumulative_total = int(message_data.get('cumulative_total_vehicles', 0))
                            current_in_roi = int(message_data.get('current_in_roi', 0))
                            speeding_vehicles_list = [v for v in vehicles if v.get('speed', 0) > 60]
                            
                            stats = {
                                'total_vehicles': cumulative_total,  # Cumulative total vehicles entered ROI
                                'speeding_count': len(speeding_vehicles_list),
                                'current_in_roi': current_in_roi  # Currently tracked in ROI
                            }
                            
                            end_of_stream = message_data.get('end_of_stream', 'false') == 'true'
                            
                            frame_count += 1
                            
                            # Route to FRAME channel (frame + ROI only, no vehicles/stats)
                            if has_frame_subs:
                                frame_data = {
                                    'video_id': video_id_int,
                                    'frame_number': frame_number_int,
                                    'timestamp': timestamp,
                                    'processed_frame': message_data.get('processed_frame', ''),
                                    'roi_polygon': roi_polygon,
                                    'end_of_stream': end_of_stream
                                }
                                
                                self.ws_frame.send(json.dumps({
                                    'type': 'processed_frame',
                                    'data': frame_data
                                }))
                                print(f"[FRAME] ✓ Frame {frame_number} → frame channel")
                            
                            # Route to ANALYTICS channel (stats + speeding vehicles only)
                            if has_analytics_subs:
                                # Filter speeding vehicles (>60 km/h)
                                speeding_vehicles = [v for v in vehicles if v.get('speed', 0) > 60]
                                
                                analytics_data = {
                                    'video_id': video_id_int,
                                    'frame_number': frame_number_int,
                                    'timestamp': timestamp,
                                    'stats': stats,
                                    'speeding_vehicles': speeding_vehicles
                                }
                                
                                self.ws_analytics.send(json.dumps({
                                    'type': 'analytics_update',
                                    'data': analytics_data
                                }))
                                print(f"[ANALYTICS] ✓ Frame {frame_number} → analytics channel (speeding: {len(speeding_vehicles)})")
                            
                            # Acknowledge message
                            self.redis_client.xack(REDIS_RESULT_STREAM, 'redis-consumer-group', message_id)
                            
                            error_count = 0
                            
                        except (websocket.WebSocketConnectionClosedException, BrokenPipeError) as e:
                            print(f"\n✗ WebSocket connection lost: {e}")
                            print("Reconnecting both channels...")
                            
                            if self.connect_to_backend():
                                print("✓ Reconnected successfully\n")
                                # Retry sending this message
                                continue
                            else:
                                print("✗ Failed to reconnect. Exiting.")
                                return
                        
                        except Exception as e:
                            error_count += 1
                            print(f"✗ Error processing frame {frame_number}: {e}")
                            
                            if error_count > 10:
                                print("Too many consecutive errors. Restarting connection...")
                                self.connect_to_backend()
                                error_count = 0
            
            except KeyboardInterrupt:
                print("\n\nShutting down consumer...")
                break
            
            except Exception as e:
                print(f"✗ Consumer error: {e}")
                time.sleep(2)
        
        if self.ws_frame:
            self.ws_frame.close()
        if self.ws_analytics:
            self.ws_analytics.close()
        self.redis_client.close()
        print(f"\nTotal frames forwarded: {frame_count}")

if __name__ == "__main__":
    try:
        # Khởi tạo consumer
        consumer = ResultConsumer()
        # Bắt đầu lắng nghe
        consumer.start_consuming()
    except Exception as e:
        print(f"Fatal Error: {e}")