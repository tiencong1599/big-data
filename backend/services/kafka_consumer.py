from kafka import KafkaConsumer
import json
import os
import time
import websocket

# Get settings from environment variables
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
KAFKA_RESULT_TOPIC = os.getenv('KAFKA_RESULT_TOPIC', 'processed-frames')
BACKEND_URL = os.getenv('BACKEND_URL', 'http://video_streaming_backend:8686')

class ResultConsumer:
    """
    Consumer to read processed frames from Kafka and forward to backend WebSocket handler
    This runs as a separate service alongside the Tornado backend
    """
    
    def __init__(self):
        print(f"Initializing Kafka consumer...")
        print(f"  Bootstrap servers: {KAFKA_BOOTSTRAP_SERVERS}")
        print(f"  Topic: {KAFKA_RESULT_TOPIC}")
        print(f"  Backend URL: {BACKEND_URL}")
        
        self.consumer = KafkaConsumer(
            KAFKA_RESULT_TOPIC,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='latest',
            enable_auto_commit=True,
            group_id='kafka-consumer-group',
            # CRITICAL CHANGES: Force single-message consumption
            fetch_min_bytes=1,              # Don't wait for batch size
            fetch_max_wait_ms=100,          # Max 100ms wait time
            max_poll_records=1,             # Process 1 frame at a time
            session_timeout_ms=30000,
            heartbeat_interval_ms=3000
        )
        # Convert HTTP URL to WebSocket URL
        ws_url = BACKEND_URL.replace('http://', 'ws://').replace('https://', 'wss://')
        self.backend_ws_url = f"{ws_url}/ws/backend_processed_frame"
        self.ws = None
        self.reconnect_delay = 5
    
    def connect_to_backend(self):
        """Establish WebSocket connection to backend unified channel"""
        max_retries = 5
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                print(f"Attempting to connect to {self.backend_ws_url}...")
                self.ws = websocket.create_connection(
                    self.backend_ws_url,
                    timeout=10
                )
                print(f"✓ Connected to backend WebSocket channel")
                return True
            except Exception as e:
                retry_count += 1
                print(f"✗ Connection failed (attempt {retry_count}/{max_retries}): {e}")
                if retry_count < max_retries:
                    print(f"  Retrying in {self.reconnect_delay} seconds...")
                    time.sleep(self.reconnect_delay)
        
        print(f"Failed to connect after {max_retries} attempts")
        return False
    
    def start_consuming(self):
        """Consume processed frames and send to backend via WebSocket"""
        if not self.connect_to_backend():
            print("Could not establish WebSocket connection. Exiting.")
            return
        
        print(f"\nStarting to consume from {KAFKA_RESULT_TOPIC}...")
        print("Waiting for messages...\n")
        
        frame_count = 0
        error_count = 0
        
        for message in self.consumer:
            try:
                frame_data = message.value
                video_id = frame_data.get('video_id')
                frame_number = frame_data.get('frame_number', 'unknown')
                
                frame_count += 1
                
                # Send IMMEDIATELY to unified backend channel
                try:
                    self.ws.send(json.dumps({
                        'type': 'processed_frame',
                        'data': frame_data
                    }))
                    
                    # Log every frame instead of batches
                    print(f"✓ Frame {frame_number} forwarded (video {video_id})")
                    
                    error_count = 0
                    
                except (websocket.WebSocketConnectionClosedException, BrokenPipeError) as e:
                    print(f"WebSocket connection lost: {e}")
                    print("Attempting to reconnect...")
                    if self.connect_to_backend():
                        # Retry sending this frame
                        self.ws.send(json.dumps({
                            'type': 'processed_frame',
                            'data': frame_data
                        }))
                    else:
                        print("Failed to reconnect. Exiting.")
                        break
                
            except Exception as e:
                error_count += 1
                print(f"Error processing message ({error_count}): {e}")
                if error_count > 10:
                    print("Too many consecutive errors. Exiting.")
                    break
    
    def close(self):
        """Close consumer and WebSocket connections"""
        print("\nClosing consumer...")
        if self.ws:
            try:
                self.ws.close()
                print("WebSocket connection closed.")
            except Exception as e:
                print(f"Error closing WebSocket: {e}")
        
        self.consumer.close()
        print("Kafka consumer closed.")

if __name__ == "__main__":
    consumer = ResultConsumer()
    try:
        consumer.start_consuming()
    except KeyboardInterrupt:
        print("\nShutting down consumer...")
        consumer.close()
