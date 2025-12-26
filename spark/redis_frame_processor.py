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
from analytics_tracker import VehicleAnalyticsTracker  # NEW IMPORT
from violation_capture_handler import (
    ViolationCaptureHandler, 
    ViolationData,
    get_violation_handler
)  # VIOLATION CAPTURE
import visualizer
import config

# Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_INPUT_STREAM = os.getenv("REDIS_INPUT_STREAM", "video-frames")
REDIS_OUTPUT_STREAM = os.getenv("REDIS_OUTPUT_STREAM", "processed-frames")
ENABLE_VEHICLE_DETECTION = os.getenv("ENABLE_VEHICLE_DETECTION", "true").lower() == "true"

# Violation capture configuration
VIOLATION_CAPTURES_DIR = os.getenv("VIOLATION_CAPTURES_DIR", "/app/violation_captures")
SPEED_LIMIT = float(os.getenv("SPEED_LIMIT", "60.0"))  # km/h
ENABLE_VIOLATION_CAPTURE = os.getenv("ENABLE_VIOLATION_CAPTURE", "true").lower() == "true"

# Global model instances
detector = None
tracker = None
speed_estimators = {}

class FrameProcessor:
    def __init__(self, redis_client):
        # Analytics trackers per video
        self.analytics_trackers = {}
        self.redis_client = redis_client
        
        # Session tracking for violation captures
        self.session_starts = {}  # video_id -> datetime
        
        # Initialize violation capture handler (singleton)
        if ENABLE_VIOLATION_CAPTURE:
            self.violation_handler = get_violation_handler(
                capture_dir=VIOLATION_CAPTURES_DIR,
                jpeg_quality=85,
                max_queue_size=100,
                batch_size=10
            )
            print(f"[VIOLATION-CAPTURE] Enabled - Dir: {VIOLATION_CAPTURES_DIR}, Limit: {SPEED_LIMIT} km/h")
        else:
            self.violation_handler = None
            print("[VIOLATION-CAPTURE] Disabled")
    
    def initialize_models(self):
        """Initialize vehicle detection models"""
        global detector, tracker
        
        if detector is None:
            detector = VehicleDetector()
            print("Models initialized successfully")
        
        if tracker is None:
            tracker = VehicleTracker()

    def encode_to_base64(self, image):
        """Encode OpenCV image to base64 string with compression"""
        _, buffer = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 60])
        return base64.b64encode(buffer).decode('utf-8')

    def decode_from_base64(self, base64_string):
        """Decode base64 string to OpenCV image"""
        img_data = base64.b64decode(base64_string)
        nparr = np.frombuffer(img_data, np.uint8)
        return cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    def get_analytics_tracker(self, video_id):
        """Get or create analytics tracker for video"""
        if video_id not in self.analytics_trackers:
            self.analytics_trackers[video_id] = VehicleAnalyticsTracker(
                self.redis_client,
                video_id
            )
        return self.analytics_trackers[video_id]
    
    def process_frame(self, frame_data):
        """Process a single frame with vehicle detection and tracking"""
        global detector, tracker, speed_estimators

        timing = {}
        frame_start = time.time()
        
        try:
            # Initialize models if needed
            self.initialize_models()
            
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
            
            t0 = time.time()
            # Decode frame
            frame = self.decode_from_base64(frame_base64)
            timing['decode'] = (time.time() - t0) * 1000
            
            # Get configuration
            use_roi = frame_config.get('use_roi', False)
            use_homography = frame_config.get('use_homography', False)
            fps = frame_config.get('fps', 30.0)
            roi_polygon = frame_config.get('roi_polygon', [])
            homography_matrix = frame_config.get('homography_matrix')
            
            # Get camera matrix if available
            camera_matrix = frame_config.get('camera_matrix')
            
            # Initialize speed estimator for this video if needed
            if video_id not in speed_estimators:
                # Convert matrices from list to numpy array if needed
                if homography_matrix and use_homography:
                    H = np.array(homography_matrix) if isinstance(homography_matrix, list) else homography_matrix
                else:
                    # Create identity matrix if no homography
                    H = np.eye(3)
                
                # Convert camera matrix if provided
                K = None
                if camera_matrix:
                    K = np.array(camera_matrix) if isinstance(camera_matrix, list) else camera_matrix
                    print(f"  Camera matrix provided for distortion correction")
                
                # Create speed estimator with optional camera matrix
                # Note: distortion_coeffs are not yet stored in DB, using None for now
                speed_estimators[video_id] = SpeedEstimator(
                    homography_matrix=H,
                    fps=fps,
                    camera_matrix=K,
                    distortion_coeffs=None  # Future enhancement: store distortion coeffs
                )
            
            speed_estimator = speed_estimators[video_id]
            
            # 1. Detect vehicles
            t0 = time.time()
            detections = detector.detect(frame)
            timing['detection'] = (time.time() - t0) * 1000
            timing['detection_count'] = len(detections)
            print(f"  Frame {frame_number}: {len(detections)} detections from YOLO")
            
            # 2. Apply ROI filter if enabled (TEMPORARILY DISABLED FOR DEBUGGING)
            t0 = time.time()
            if use_roi and roi_polygon and len(roi_polygon) > 0:
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

            timing['roi_filter'] = (time.time() - t0) * 1000
            timing['roi_filtered_count'] = len(detections)

            # 3. Track vehicles
            t0 = time.time()
            tracks = tracker.update(frame, detections)
            print(f"  Active tracks: {len(tracks)}")
            timing['tracking'] = (time.time() - t0) * 1000
            timing['track_count'] = len(tracks)
            
            # 4. Estimate speeds (update with all tracks at once)
            t0 = time.time()
            speeds = speed_estimator.update(tracks, frame_number)
            if speeds:
                print(f"  Speeds: {[(tid, f'{s:.1f}') for tid, s in speeds.items()]}")
            timing['speed_estimation'] = (time.time() - t0) * 1000
            
            # 5. Prepare vehicle data
            t0 = time.time()
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
            timing['build_data'] = (time.time() - t0) * 1000

            # Get analytics tracker
            t0 = time.time()
            tracker_instance = self.get_analytics_tracker(video_id)

            # Update analytics with current tracks
            tracker_instance.update(tracks, timestamp / 1000)  # Convert ms to seconds
            timing['analytics'] = (time.time() - t0) * 1000

            # Set vehicle types
            for track_id, bbox in tracks:
                for det_bbox, det_conf, det_class in detections:
                    if self._bbox_iou(bbox, det_bbox) > 0.5:
                        tracker_instance.set_vehicle_type(track_id, int(det_class))
                        break
            
            # ===================================================================
            # VIOLATION CAPTURE - Capture frames for speeding vehicles
            # ===================================================================
            t0 = time.time()
            violations_captured = 0
            
            if self.violation_handler and ENABLE_VIOLATION_CAPTURE:
                # Get or create session start for this video
                if video_id not in self.session_starts:
                    from datetime import datetime
                    self.session_starts[video_id] = datetime.utcnow()
                
                session_start = self.session_starts[video_id]
                
                # Check each tracked vehicle for speed violations
                for track_id, bbox in tracks:
                    speed = speeds.get(track_id, 0.0)
                    
                    # Check if should capture (handles deduplication internally)
                    if self.violation_handler.should_capture(
                        video_id=video_id,
                        track_id=track_id,
                        speed=speed,
                        speed_limit=SPEED_LIMIT,
                        session_start=session_start
                    ):
                        # Get vehicle class info
                        class_id = 2  # Default to car
                        confidence = 0.0
                        for det_bbox, det_conf, det_class in detections:
                            if self._bbox_iou(bbox, det_bbox) > 0.5:
                                class_id = int(det_class)
                                confidence = float(det_conf)
                                break
                        
                        vehicle_type = ViolationCaptureHandler.get_vehicle_type(class_id)
                        
                        # Create violation data
                        violation_data = ViolationData(
                            video_id=video_id,
                            track_id=int(track_id),
                            speed=float(speed),
                            speed_limit=SPEED_LIMIT,
                            vehicle_type=vehicle_type,
                            class_id=class_id,
                            confidence=confidence,
                            frame_number=frame_number,
                            bbox={
                                'x1': int(bbox[0]),
                                'y1': int(bbox[1]),
                                'x2': int(bbox[2]),
                                'y2': int(bbox[3])
                            },
                            video_timestamp=timestamp / 1000.0,
                            session_start=session_start
                        )
                        
                        # Queue for capture (non-blocking)
                        if self.violation_handler.capture_violation(frame, violation_data):
                            violations_captured += 1
            
            timing['violation_capture'] = (time.time() - t0) * 1000
            timing['violations_captured'] = violations_captured
            
            # 6. Visualization
            t0 = time.time()
            annotated_frame = visualizer.draw_results(frame, tracks, speeds)
            timing['visualization'] = (time.time() - t0) * 1000

            # Draw ROI polygon
            if roi_polygon and len(roi_polygon) > 0:
                roi_points = np.array(roi_polygon, dtype=np.int32)
                cv2.polylines(annotated_frame, [roi_points], True, (0, 255, 0), 2)
            
            # Encode result
            t0 = time.time()
            processed_frame_base64 = self.encode_to_base64(annotated_frame)
            timing['encode'] = (time.time() - t0) * 1000
            timing['encoded_size_kb'] = len(processed_frame_base64) / 1024

            total_time = (time.time() - frame_start) * 1000
            
            timing['total'] = total_time
            timing['theoretical_fps'] = 1000 / total_time if total_time > 0 else 0
            
            # ===================================================================
            # PRINT DETAILED TIMING REPORT
            # ===================================================================
            print(f"\n{'='*70}")
            print(f"[PERFORMANCE] Frame {frame_number} | Video {video_id}")
            print(f"{'='*70}")
            print(f"  Decode:           {timing['decode']:7.2f}ms")
            print(f"  Detection:        {timing['detection']:7.2f}ms  ({timing['detection_count']} objects)")
            print(f"  ROI Filter:       {timing['roi_filter']:7.2f}ms  ({timing['roi_filtered_count']} after filter)")
            print(f"  Tracking:         {timing['tracking']:7.2f}ms  ({timing['track_count']} tracks)")
            print(f"  Speed Estimation: {timing['speed_estimation']:7.2f}ms")
            print(f"  Build Data:       {timing['build_data']:7.2f}ms")
            print(f"  Visualization:    {timing['visualization']:7.2f}ms")
            print(f"  Encode:           {timing['encode']:7.2f}ms  ({timing['encoded_size_kb']:.1f}KB)")
            print(f"  Analytics:        {timing['analytics']:7.2f}ms")
            print(f"  Violation Cap:    {timing.get('violation_capture', 0):7.2f}ms  ({timing.get('violations_captured', 0)} captured)")
            print(f"  {'─'*70}")
            print(f"  TOTAL:            {timing['total']:7.2f}ms  ({timing['theoretical_fps']:.1f} FPS)")
            print(f"{'='*70}\n")

            # Get cumulative analytics metrics
            analytics_metrics = tracker_instance.get_current_metrics()

            result = {
                'video_id': str(video_id),
                'frame_number': str(frame_number),
                'timestamp': str(timestamp),
                'end_of_stream': 'false',
                'processed_frame': processed_frame_base64,
                'vehicles': json.dumps(vehicles),
                'roi_polygon': json.dumps(roi_polygon),
                'total_vehicles': str(len(vehicles)),  # Current frame count
                'cumulative_total_vehicles': str(analytics_metrics['total_vehicles_entered']),  # NEW: Cumulative total
                'current_in_roi': str(analytics_metrics['current_vehicles_in_roi']),  # NEW: Current in ROI
                'has_homography': str(use_homography and homography_matrix is not None).lower(),
                'has_camera_matrix': 'false',
                'error': ''
            }
            
            return result
        
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

    def _bbox_iou(self, boxA, boxB):
        """Calculate IoU between two bounding boxes"""
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])
        
        interArea = max(0, xB - xA) * max(0, yB - yA)
        
        boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
        boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
        
        iou = interArea / float(boxAArea + boxBArea - interArea + 1e-6)
        return iou
    
    def finalize_video_analytics(self, video_id):
        """Called when video processing completes"""
        if video_id in self.analytics_trackers:
            tracker = self.analytics_trackers[video_id]
            
            # Dump to PostgreSQL
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker
            
            engine = create_engine(os.getenv('DATABASE_URL'))
            Session = sessionmaker(bind=engine)
            db = Session()
            
            try:
                tracker.finalize_and_dump_to_db(db)
                print(f"[ANALYTICS] ✓ Finalized analytics for video {video_id}")
            finally:
                db.close()
            
            # Remove tracker
            del self.analytics_trackers[video_id]

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
    
    # Initialize frame processor with Redis client
    processor = FrameProcessor(redis_client)
    processor.initialize_models()
    
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
                block=100  # 0.1 second timeout
            )
            
            if not messages:
                continue
            
            for stream_name, stream_messages in messages:
                for message_id, frame_data in stream_messages:
                    start_time = time.time()
                    
                    # Process frame IMMEDIATELY
                    result = processor.process_frame(frame_data)
                    
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
