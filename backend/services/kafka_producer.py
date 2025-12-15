import cv2
import json
import base64
import time
from kafka import KafkaProducer
from config.settings import KAFKA_BOOTSTRAP_SERVERS, KAFKA_VIDEO_TOPIC
from models.video import get_video_config

class VideoFrameProducer:
    def __init__(self):
        self.producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            max_request_size=10485760  # 10MB
        )
    
    def stream_video(self, video_id, video_path):
        """Stream video frames with configuration to Kafka"""
        cap = cv2.VideoCapture(video_path)
        frame_number = 0
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            # CRITICAL CHANGE: Reduce quality + resize for faster processing
            frame = cv2.resize(frame, (640, 480))  # Reduce resolution
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
            frame_base64 = base64.b64encode(buffer).decode('utf-8')
            
            # Prepare message with full configuration from database
            message = {
                'video_id': video_id,
                'frame_number': frame_number,
                'frame_data': frame_base64,
                'timestamp': int(time.time() * 1000),
                'config': get_video_config(video_id)
            }
            
            # Send to Kafka
            self.producer.send(KAFKA_VIDEO_TOPIC, value=message)
            frame_number += 1
            
        # Send end-of-stream marker
        self.producer.send(KAFKA_VIDEO_TOPIC, value={
            'video_id': video_id,
            'frame_number': frame_number,
            'frame_data': '',
            'end_of_stream': True
        })
        self.producer.flush()
        
        print(f"Finished streaming {frame_number} frames for video {video_id}")
        
        cap.release()
    
    def close(self):
        self.producer.close()
