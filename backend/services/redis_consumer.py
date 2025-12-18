import redis
import json
import os
import time
import websocket

# Get settings from environment variables
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_RESULT_STREAM = 'processed-frames'
BACKEND_URL = os.getenv('BACKEND_URL', 'http://video_streaming_backend:8686')

class ResultConsumer:
    """
    Consumer to read processed frames from Redis Streams and forward to backend WebSocket handler
    This runs as a separate service alongside the Tornado backend
    """
    
    def __init__(self):
        print(f"Initializing Redis consumer...")
        
        self.redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True  # Metadata is JSON strings
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
        self.backend_ws_url = f"{ws_url}/ws/backend_processed_frame"
        self.ws = None
        self.reconnect_delay = 5
        self.last_id = '>'  # Read only new messages
    
    def connect_to_backend(self):
        """Establish WebSocket connection to backend unified channel"""
        max_retries = 5
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                retry_count += 1
                print(f"Attempting to connect to {self.backend_ws_url}...")
                self.ws = websocket.create_connection(
                    self.backend_ws_url,
                    timeout=10
                )
                print("✓ Connected to backend WebSocket channel\n")
                return True
                
            except Exception as e:
                print(f"✗ Connection failed (attempt {retry_count}/{max_retries}): {e}")
                if retry_count < max_retries:
                    print(f"  Retrying in {self.reconnect_delay} seconds...")
                    time.sleep(self.reconnect_delay)
        
        return False
    
    def start_consuming(self):
        """Consume lightweight metadata and forward to backend"""
        if not self.connect_to_backend():
            print("Could not establish WebSocket connection. Exiting.")
            return
        
        print(f"Starting to consume from {REDIS_RESULT_STREAM}...\n")
        
        frame_count = 0
        last_id = '>'
        
        while True:
            try:
                # Read messages from stream (blocking with 1000ms timeout)
                messages = self.redis_client.xreadgroup(
                    groupname='redis-consumer-group',
                    consumername='consumer-1',
                    streams={REDIS_RESULT_STREAM: last_id},
                    count=1,  # Process ONE message at a time
                    block=1000  # 1 second block timeout
                )
                
                if not messages:
                    continue
                
                # Process each message immediately
                for stream_name, stream_messages in messages:
                    for message_id, message_data in stream_messages:
                        try:
                            # Parse lightweight metadata (2-3 KB)
                            video_id = int(message_data.get('video_id', 0))
                            frame_number = int(message_data.get('frame_number', 0))
                            
                            # Reconstruct metadata
                            frame_data = {
                                'video_id': video_id,
                                'frame_number': frame_number,
                                'timestamp': int(message_data.get('timestamp', 0)),
                                'original_resolution': json.loads(message_data.get('original_resolution', '{}')),
                                'vehicles': json.loads(message_data.get('vehicles', '[]')),
                                'total_vehicles': int(message_data.get('total_vehicles', 0)),
                                'processing_time_ms': float(message_data.get('processing_time_ms', 0)),
                                'has_homography': message_data.get('has_homography', 'false') == 'true',
                                'roi_polygon': json.loads(message_data.get('roi_polygon', 'null'))
                            }
                            
                            frame_count += 1
                            
                            # Send to backend
                            self.ws.send(json.dumps({
                                'type': 'processed_frame',
                                'data': frame_data
                            }))
                            
                            # Acknowledge
                            self.redis_client.xack(REDIS_RESULT_STREAM, 'redis-consumer-group', message_id)
                            
                            # Log every frame
                            print(f"✓ Frame {frame_number} forwarded (video {video_id}, {len(frame_data['vehicles'])} vehicles)")
                        
                        except Exception as e:
                            print(f"✗ Error processing frame: {e}")
            
            except KeyboardInterrupt:
                print("\n🛑 Shutting down consumer...")
                break
            except Exception as e:
                print(f"✗ Consumer error: {e}")
                time.sleep(2)
        
        if self.ws:
            self.ws.close()
        self.redis_client.close()

if __name__ == "__main__":
    consumer = ResultConsumer()
    consumer.start_consuming()
