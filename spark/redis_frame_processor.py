import redis
import json
import base64
import cv2
import numpy as np
import os
import time
from detector import VehicleDetector
from tracker import VehicleTracker
from speed_estimator import SpeedEstimator
import visualizer
import config

# Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_INPUT_STREAM = os.getenv("REDIS_INPUT_STREAM", "video-frames")
REDIS_OUTPUT_STREAM = os.getenv("REDIS_OUTPUT_STREAM", "processed-frames")
ENABLE_VEHICLE_DETECTION = os.getenv("ENABLE_VEHICLE_DETECTION", "true").lower() == "true"

# Global model instances
detector = None
tracker = None
speed_estimators = {}

def initialize_models():
    """Initialize vehicle detection models"""
    global detector, tracker
    
    if detector is None:
        detector = VehicleDetector()
        print("Models initialized successfully")
    
    if tracker is None:
        tracker = VehicleTracker()

def encode_to_base64(image):
    """Encode OpenCV image to base64 string with compression"""
    _, buffer = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 60])
    return base64.b64encode(buffer).decode('utf-8')

def decode_from_base64(base64_string):
    """Decode base64 string to OpenCV image"""
    img_data = base64.b64decode(base64_string)
    nparr = np.frombuffer(img_data, np.uint8)
    return cv2.imdecode(nparr, cv2.IMREAD_COLOR)

def process_frame(frame_data):
    """Process a single frame with vehicle detection and tracking"""
    global detector, tracker, speed_estimators
    
    try:
        # Initialize models if needed
        initialize_models()
        
        # Parse input
        video_id = int(frame_data['video_id'])
        frame_number = int(frame_data['frame_number'])
        frame_base64 = frame_data['frame_data']
        timestamp = int(frame_data['timestamp'])
        
        # Handle config - may be missing or string
        config_data = frame_data.get('config')
        if config_data:
            frame_config = json.loads(config_data) if isinstance(config_data, str) else config_data
        else:
            # Default config if missing
            frame_config = {
                'use_roi': False,
                'use_homography': False,
                'fps': 30.0,
                'roi_polygon': [],
                'homography_matrix': None
            }
        
        # Check for end-of-stream
        if frame_data.get('end_of_stream') == 'true' or not frame_base64:
            return {
                'video_id': str(video_id),
                'frame_number': str(frame_number),
                'timestamp': str(timestamp),
                'end_of_stream': 'true',
                'processed_frame': '',
                'vehicles': '[]',
                'roi_polygon': '[]',
                'total_vehicles': '0',
                'has_homography': 'false',
                'has_camera_matrix': 'false',
                'error': ''
            }
        
        print(f"Processing frame {frame_number} for video {video_id}")
        print(f"  Config: ROI={frame_config.get('use_roi')}, H={frame_config.get('use_homography')}, FPS={frame_config.get('fps')}")
        
        # Decode frame
        frame = decode_from_base64(frame_base64)
        
        # Get configuration
        use_roi = frame_config.get('use_roi', False)
        use_homography = frame_config.get('use_homography', False)
        fps = frame_config.get('fps', 30.0)
        roi_polygon = frame_config.get('roi_polygon', [])
        homography_matrix = frame_config.get('homography_matrix')
        
        # Initialize speed estimator for this video if needed
        if video_id not in speed_estimators:
            # SpeedEstimator only takes homography_matrix and fps
            if homography_matrix and use_homography:
                # Convert homography matrix from list to numpy array
                H = np.array(homography_matrix) if isinstance(homography_matrix, list) else homography_matrix
                speed_estimators[video_id] = SpeedEstimator(
                    homography_matrix=H,
                    fps=fps
                )
            else:
                # Create dummy estimator with identity matrix if no homography
                identity_matrix = np.eye(3)
                speed_estimators[video_id] = SpeedEstimator(
                    homography_matrix=identity_matrix,
                    fps=fps
                )
        
        speed_estimator = speed_estimators[video_id]
        
        # 1. Detect vehicles
        detections = detector.detect(frame)
        print(f"  Frame {frame_number}: {len(detections)} detections from YOLO")
        
        # 2. Apply ROI filter if enabled (TEMPORARILY DISABLED FOR DEBUGGING)
        if False and use_roi and roi_polygon and len(roi_polygon) > 0:
            print(f"  Frame dimensions: {frame.shape[1]}x{frame.shape[0]} (WxH)")
            print(f"  ROI polygon: {roi_polygon}")
            
            roi_mask = np.zeros(frame.shape[:2], dtype=np.uint8)
            roi_points = np.array(roi_polygon, dtype=np.int32)
            cv2.fillPoly(roi_mask, [roi_points], 255)
            
            filtered_detections = []
            for i, det in enumerate(detections):
                # det format: ([x1, y1, x2, y2], confidence, class_id)
                bbox, conf, class_id = det
                x1, y1, x2, y2 = bbox
                center_x, center_y = (x1 + x2) // 2, (y1 + y2) // 2
                
                # Check bounds to prevent array access errors
                if 0 <= center_y < frame.shape[0] and 0 <= center_x < frame.shape[1]:
                    is_inside = roi_mask[center_y, center_x] > 0
                    if i < 3:  # Log first 3 detections
                        print(f"    Det[{i}]: bbox=[{x1:.0f},{y1:.0f},{x2:.0f},{y2:.0f}] center=({center_x},{center_y}) inside={is_inside} roi_val={roi_mask[center_y, center_x]}")
                    if is_inside:
                        filtered_detections.append(det)
                else:
                    print(f"    Det[{i}]: center=({center_x},{center_y}) OUT OF BOUNDS!")
                    
            detections = filtered_detections
            print(f"  After ROI filter: {len(detections)} detections remain")
        
        # 3. Track vehicles
        tracks = tracker.update(frame, detections)
        print(f"  Active tracks: {len(tracks)}")
        
        # 4. Estimate speeds (update with all tracks at once)
        speeds = speed_estimator.update(tracks, frame_number)
        if speeds:
            print(f"  Speeds: {[(tid, f'{s:.1f}') for tid, s in speeds.items()]}")
        
        # 5. Prepare vehicle data
        vehicles = []
        for track_id, bbox in tracks:
            x1, y1, x2, y2 = bbox
            speed = speeds.get(track_id, 0.0)
            
            vehicles.append({
                'track_id': int(track_id),
                'bbox': {
                    'x1': int(x1),
                    'y1': int(y1),
                    'x2': int(x2),
                    'y2': int(y2)
                },
                'speed': float(speed),
                'speed_unit': config.SPEED_UNIT
            })
        
        # 6. Visualization
        annotated_frame = visualizer.draw_results(frame, tracks, speeds)
        
        # Draw ROI polygon
        if roi_polygon and len(roi_polygon) > 0:
            roi_points = np.array(roi_polygon, dtype=np.int32)
            cv2.polylines(annotated_frame, [roi_points], True, (0, 255, 0), 2)
        
        # Encode result
        processed_frame_base64 = encode_to_base64(annotated_frame)
        
        return {
            'video_id': str(video_id),
            'frame_number': str(frame_number),
            'timestamp': str(timestamp),
            'end_of_stream': 'false',
            'processed_frame': processed_frame_base64,
            'vehicles': json.dumps(vehicles),
            'roi_polygon': json.dumps(roi_polygon),
            'total_vehicles': str(len(vehicles)),
            'has_homography': str(use_homography and homography_matrix is not None).lower(),
            'has_camera_matrix': 'false',
            'error': ''
        }
        
    except Exception as e:
        print(f"✗ Error processing frame: {e}")
        import traceback
        traceback.print_exc()
        
        return {
            'video_id': str(frame_data.get('video_id', 0)),
            'frame_number': str(frame_data.get('frame_number', 0)),
            'timestamp': str(frame_data.get('timestamp', 0)),
            'end_of_stream': 'false',
            'processed_frame': '',
            'vehicles': '[]',
            'roi_polygon': '[]',
            'total_vehicles': '0',
            'has_homography': 'false',
            'has_camera_matrix': 'false',
            'error': str(e)
        }

def main():
    """Real-time Redis Streams processor - one frame at a time"""
    print(f"=" * 60)
    print("REDIS STREAMS REAL-TIME VIDEO PROCESSOR")
    print(f"=" * 60)
    print(f"Redis Host: {REDIS_HOST}:{REDIS_PORT}")
    print(f"Input Stream: {REDIS_INPUT_STREAM}")
    print(f"Output Stream: {REDIS_OUTPUT_STREAM}")
    print(f"Vehicle Detection: {ENABLE_VEHICLE_DETECTION}")
    print(f"=" * 60)
    
    # Connect to Redis
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=0,
        decode_responses=True,
        socket_keepalive=True
    )
    
    # Create consumer group
    try:
        redis_client.xgroup_create(
            REDIS_INPUT_STREAM,
            'spark-processor-group',
            id='0',
            mkstream=True
        )
        print("✓ Created consumer group 'spark-processor-group'")
    except redis.exceptions.ResponseError as e:
        if 'BUSYGROUP' in str(e):
            print("✓ Consumer group already exists")
        else:
            raise
    
    print("\n🚀 Starting real-time frame processing...\n")
    
    frame_count = 0
    last_id = '>'
    
    try:
        while True:
            # Read ONE message at a time (blocking with timeout)
            messages = redis_client.xreadgroup(
                groupname='spark-processor-group',
                consumername='processor-1',
                streams={REDIS_INPUT_STREAM: last_id},
                count=1,  # Process ONE frame at a time
                block=1000  # 1 second timeout
            )
            
            if not messages:
                continue
            
            for stream_name, stream_messages in messages:
                for message_id, frame_data in stream_messages:
                    start_time = time.time()
                    
                    # Process frame IMMEDIATELY
                    result = process_frame(frame_data)
                    
                    # Send result IMMEDIATELY to output stream
                    redis_client.xadd(
                        REDIS_OUTPUT_STREAM,
                        result,
                        maxlen=1000
                    )
                    
                    # Acknowledge message
                    redis_client.xack(REDIS_INPUT_STREAM, 'spark-processor-group', message_id)
                    
                    frame_count += 1
                    processing_time = (time.time() - start_time) * 1000
                    
                    if frame_count % 10 == 0:
                        print(f"✓ Processed {frame_count} frames | Last: frame {result['frame_number']} ({processing_time:.1f}ms)")
    
    except KeyboardInterrupt:
        print("\n\n⏹ Shutting down processor...")
    
    finally:
        redis_client.close()
        print(f"✓ Total frames processed: {frame_count}")

if __name__ == "__main__":
    main()
