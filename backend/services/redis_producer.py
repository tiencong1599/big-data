import cv2
import json
import base64
import time
import redis
import os
from models.video import get_video_config

REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_VIDEO_STREAM = os.getenv('REDIS_VIDEO_STREAM', 'video-frames')

class VideoFrameProducer:
    def __init__(self):
        self.redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=0,
            decode_responses=False,  # Keep binary for efficiency
            socket_keepalive=True,
            socket_connect_timeout=5
        )
        print(f"[REDIS-PRODUCER] Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
    
    def stream_video(self, video_id, video_path):
        """Stream video frames with configuration to Redis Streams"""
        cap = cv2.VideoCapture(video_path)
        frame_number = 0
        
        print(f"[REDIS-PRODUCER] Starting video stream for video {video_id}")
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            # Reduce quality + resize for faster processing
            frame = cv2.resize(frame, (640, 480))
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
            frame_base64 = base64.b64encode(buffer).decode('utf-8')
            
            # Prepare message with full configuration from database
            message = {
                'video_id': str(video_id),
                'frame_number': str(frame_number),
                'frame_data': frame_base64,
                'timestamp': str(int(time.time() * 1000)),
                'config': json.dumps(get_video_config(video_id))
            }
            
            # Send to Redis Stream (XADD) - real-time, no batching
            message_id = self.redis_client.xadd(
                REDIS_VIDEO_STREAM,
                message,
                maxlen=1000  # Keep last 1000 messages to prevent memory overflow
            )
            
            if frame_number % 100 == 0:
                print(f"[REDIS-PRODUCER] Sent frame {frame_number} (msg_id: {message_id.decode()})")
            
            frame_number += 1
        
        # Send end-of-stream marker
        self.redis_client.xadd(
            REDIS_VIDEO_STREAM,
            {
                'video_id': str(video_id),
                'frame_number': str(frame_number),
                'frame_data': '',
                'end_of_stream': 'true',
                'timestamp': str(int(time.time() * 1000))
            },
            maxlen=1000
        )
        
        cap.release()
        print(f"[REDIS-PRODUCER] Completed video stream for video {video_id}, total frames: {frame_number}")
        print(f"[REDIS-PRODUCER] Stream '{REDIS_VIDEO_STREAM}' length: {self.redis_client.xlen(REDIS_VIDEO_STREAM)}")
    
    def close(self):
        self.redis_client.close()
