import redis
import json
import time
import cv2
import numpy as np
from detector import VehicleDetector
from tracker import VehicleTracker
from speed_estimator import SpeedEstimator
import config
import os

# Redis Configuration
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_INPUT_STREAM = 'video-frames'
REDIS_OUTPUT_STREAM = 'processed-frames'

# Model Configuration (EASY SWITCHING)
MODEL_PATH = os.getenv('MODEL_PATH', 'yolov8s.engine')  # Change to yolov8n.engine for faster FPS
PROCESS_EVERY_N_FRAMES = int(os.getenv('FRAME_SKIP', 1))  # Process every Nth frame (1 = all frames)

class FrameProcessor:
    def __init__(self):
        print(f"🚀 Initializing FrameProcessor (Full CSR - reading from video file)")
        print(f"   Model: {MODEL_PATH}")
        print(f"   Frame Skip: {PROCESS_EVERY_N_FRAMES}")
        
        # Redis connection
        self.redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=False  # Binary mode for metadata INPUT
        )
        
        # Initialize models
        print("Loading YOLO detector...")
        self.detector = VehicleDetector(model_path=MODEL_PATH)
        
        print("Loading tracker...")
        self.tracker = VehicleTracker()
        
        # Speed estimator per video
        self.speed_estimators = {}
        
        # Video capture cache (Full CSR - read directly from file)
        self.video_captures = {}
        
        # Video path cache (for backward compatibility with old Redis messages)
        self.video_path_cache = {}
        
        # Create consumer group
        try:
            self.redis_client.xgroup_create(
                REDIS_INPUT_STREAM,
                'processor-group',
                id='0',
                mkstream=True
            )
            print("✓ Created consumer group 'processor-group'")
        except redis.exceptions.ResponseError as e:
            if 'BUSYGROUP' in str(e):
                print("✓ Consumer group already exists")
            else:
                raise
        
        print("✓ FrameProcessor initialized (Full CSR mode)\n")
    
    def get_video_path_from_db(self, video_id):
        """
        Fetch video path from PostgreSQL database (backward compatibility).
        
        This is used when old Redis messages don't have video_path in config.
        
        Args:
            video_id: Video ID
        
        Returns:
            str: Video file path or None if not found
        """
        # Check cache first
        if video_id in self.video_path_cache:
            return self.video_path_cache[video_id]
        
        try:
            import psycopg2
            
            # Database connection (use environment variables)
            DB_HOST = os.getenv('DB_HOST', 'localhost')
            DB_PORT = os.getenv('DB_PORT', '5432')
            DB_NAME = os.getenv('DB_NAME', 'video_processing')
            DB_USER = os.getenv('DB_USER', 'postgres')
            DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')
            
            conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD
            )
            
            cursor = conn.cursor()
            cursor.execute("SELECT file_path FROM videos WHERE id = %s", (video_id,))
            result = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            if result:
                video_path = result[0]
                # Cache for future use
                self.video_path_cache[video_id] = video_path
                print(f"✓ Fetched video path from DB for video {video_id}: {video_path}")
                return video_path
            else:
                print(f"✗ Video {video_id} not found in database")
                return None
                
        except Exception as e:
            print(f"✗ Error fetching video path from DB: {str(e)}")
            return None
    
    def get_video_capture(self, video_id, video_path):
        """
        Get or create video capture for reading frames directly from file (Full CSR)
        
        Args:
            video_id: Video ID
            video_path: Full path to video file
        
        Returns:
            cv2.VideoCapture object
        """
        if video_id not in self.video_captures:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise ValueError(f"Could not open video file: {video_path}")
            self.video_captures[video_id] = cap
            print(f"✓ Opened video capture for video {video_id}: {video_path}")
        return self.video_captures[video_id]
    
    def read_frame_from_video(self, video_id, video_path, frame_number):
        """
        Read frame directly from video file (Full CSR - NO BASE64!)
        
        Args:
            video_id: Video ID
            video_path: Full path to video file
            frame_number: Frame number to read
        
        Returns:
            frame: OpenCV frame (BGR)
        """
        cap = self.get_video_capture(video_id, video_path)
        
        # Seek to frame number
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
        ret, frame = cap.read()
        
        if not ret:
            raise ValueError(f"Could not read frame {frame_number} from video {video_id}")
        
        return frame
    
    def get_speed_estimator(self, video_id, homography_matrix, fps):
        """Get or create speed estimator for video"""
        if video_id not in self.speed_estimators:
            if homography_matrix:
                H = np.array(homography_matrix, dtype=np.float32)
                self.speed_estimators[video_id] = SpeedEstimator(H, fps=fps)
                print(f"✓ Created SpeedEstimator for video {video_id}")
            else:
                self.speed_estimators[video_id] = None
        return self.speed_estimators[video_id]
    
    def process_frame(self, frame_data):
        """
        Process frame and return METADATA ONLY (no image)
        
        Returns:
        {
            'video_id': 1,
            'frame_number': 42,
            'timestamp': 1703001234567,
            'original_resolution': {'width': 1920, 'height': 1080},
            'vehicles': [
                {
                    'track_id': 5,
                    'bbox': {'x1': 100, 'y1': 200, 'x2': 300, 'y2': 400},
                    'class_id': 2,
                    'confidence': 0.95,
                    'speed': 45.3,
                    'speed_unit': 'km/h'
                },
                ...
            ],
            'total_vehicles': 3,
            'processing_time_ms': 23.5
        }
        """
        start_time = time.time()
        
        try:
            # Extract metadata
            video_id = int(frame_data.get(b'video_id', 0))
            frame_number = int(frame_data.get(b'frame_number', 0))
            timestamp = int(frame_data.get(b'timestamp', 0))
            
            # Decode configuration
            config_json = frame_data.get(b'config', b'{}')
            config_data = json.loads(config_json)
            
            roi_polygon = config_data.get('roi_polygon')
            homography_matrix = config_data.get('homography_matrix')
            fps = config_data.get('fps', 30.0)
            video_path = config_data.get('video_path')  # Full CSR: get video path from config
            
            # Backward compatibility: If video_path not in config, check cache then database
            if not video_path:
                # Check cache first (avoid DB query if already cached)
                if video_id in self.video_path_cache:
                    video_path = self.video_path_cache[video_id]
                else:
                    # Cache miss - query database once per video
                    print(f"⚠️ video_path missing in config for video {video_id}, fetching from database...")
                    video_path = self.get_video_path_from_db(video_id)
                    
                    if not video_path:
                        raise ValueError(f"No video_path in config and failed to fetch from database for video {video_id}")
            
            # Full CSR: Read frame directly from video file (NO BASE64!)
            frame = self.read_frame_from_video(video_id, video_path, frame_number)
            
            if frame is None:
                raise ValueError(f"Failed to read frame {frame_number} from {video_path}")
            
            # Get original resolution
            original_height, original_width = frame.shape[:2]
            
            # Convert to RGB for YOLO
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # 1. YOLO Detection (at ORIGINAL resolution)
            detections = self.detector.detect(frame_rgb)
            
            # 2. Filter by ROI
            if roi_polygon and len(roi_polygon) > 0:
                filtered_detections = []
                for detection in detections:
                    bbox, conf, class_id = detection
                    x1, y1, x2, y2 = bbox
                    center_x = (x1 + x2) / 2
                    center_y = y2  # Bottom center
                    
                    if self._point_in_polygon((center_x, center_y), roi_polygon):
                        filtered_detections.append(detection)
                detections = filtered_detections
            
            # 3. Tracking
            tracks = self.tracker.update(frame_rgb, detections)
            
            # 4. Speed Estimation
            speeds = {}
            estimator = self.get_speed_estimator(video_id, homography_matrix, fps)
            if estimator:
                speeds = estimator.update(tracks, frame_number)
            
            # 5. Build LIGHTWEIGHT metadata (NO IMAGE DATA)
            vehicles = []
            for track_id, bbox in tracks:
                x1, y1, x2, y2 = bbox
                speed = speeds.get(track_id, 0.0)
                
                # Find original detection for confidence and class_id
                class_id = 2  # Default: car
                confidence = 0.9
                for det_bbox, det_conf, det_class in detections:
                    if self._bbox_iou(bbox, det_bbox) > 0.5:
                        class_id = int(det_class)
                        confidence = float(det_conf)
                        break
                
                vehicles.append({
                    'track_id': int(track_id),
                    'bbox': {
                        'x1': int(x1),
                        'y1': int(y1),
                        'x2': int(x2),
                        'y2': int(y2)
                    },
                    'class_id': class_id,
                    'confidence': round(confidence, 2),
                    'speed': round(speed, 1),
                    'speed_unit': config.SPEED_UNIT
                })
            
            processing_time = (time.time() - start_time) * 1000
            
            # Return METADATA ONLY (2-3 KB vs 2 MB)
            result = {
                'video_id': video_id,
                'frame_number': frame_number,
                'timestamp': timestamp,
                'original_resolution': {
                    'width': original_width,
                    'height': original_height
                },
                'vehicles': vehicles,
                'total_vehicles': len(vehicles),
                'processing_time_ms': round(processing_time, 1),
                'has_homography': homography_matrix is not None,
                'roi_polygon': roi_polygon
            }
            
            return result
            
        except Exception as e:
            print(f"❌ Error processing frame {frame_number}: {e}")
            import traceback
            traceback.print_exc()
            return {
                'video_id': video_id,
                'frame_number': frame_number,
                'error': str(e)
            }
    
    def _point_in_polygon(self, point, polygon):
        """Ray casting algorithm for point-in-polygon test"""
        x, y = point
        n = len(polygon)
        inside = False
        
        p1x, p1y = polygon[0]
        for i in range(1, n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        
        return inside
    
    def _bbox_iou(self, boxA, boxB):
        """Calculate IoU between two bounding boxes"""
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])
        
        interArea = max(0, xB - xA) * max(0, yB - yA)
        
        boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
        boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
        
        iou = interArea / float(boxAArea + boxBArea - interArea)
        return iou
    
    def start_processing(self):
        """Main processing loop"""
        print("🎬 Starting frame processing...\n")
        
        last_id = '>'
        frame_count = 0
        processed_count = 0
        
        while True:
            try:
                # Read from Redis Stream
                messages = self.redis_client.xreadgroup(
                    groupname='processor-group',
                    consumername='processor-1',
                    streams={REDIS_INPUT_STREAM: last_id},
                    count=1,
                    block=1000
                )
                
                if not messages:
                    continue
                
                for stream_name, stream_messages in messages:
                    for message_id, frame_data in stream_messages:
                        frame_count += 1
                        
                        # Frame skipping for performance
                        if frame_count % PROCESS_EVERY_N_FRAMES != 0:
                            # Acknowledge skipped frame
                            self.redis_client.xack(REDIS_INPUT_STREAM, 'processor-group', message_id)
                            continue
                        
                        # Process frame
                        result = self.process_frame(frame_data)
                        processed_count += 1
                        
                        # Send METADATA ONLY to output stream
                        # Redis XADD requires flat key-value pairs (no nested dicts)
                        # JSON-serialize nested structures
                        redis_message = {
                            'video_id': str(result['video_id']),
                            'frame_number': str(result['frame_number']),
                            'timestamp': str(result.get('timestamp', 0)),
                            'vehicles': json.dumps(result.get('vehicles', [])),
                            'total_vehicles': str(result.get('total_vehicles', 0)),
                            'processing_time_ms': str(result.get('processing_time_ms', 0)),
                            'original_resolution': json.dumps(result.get('original_resolution', {})),
                            'has_homography': str(result.get('has_homography', False)),
                            'roi_polygon': json.dumps(result.get('roi_polygon')) if result.get('roi_polygon') else '[]',
                            'error': str(result.get('error', '')) if 'error' in result else ''
                        }
                        
                        self.redis_client.xadd(
                            REDIS_OUTPUT_STREAM,
                            redis_message,
                            maxlen=1000
                        )
                        
                        # Acknowledge message
                        self.redis_client.xack(REDIS_INPUT_STREAM, 'processor-group', message_id)
                        
                        # Progress logging (each frame)
                        print(f"✓ Frame {result['frame_number']} | video {result['video_id']} | {result.get('total_vehicles', 0)} vehicles | {result['processing_time_ms']:.1f}ms")
            
            except KeyboardInterrupt:
                print("\n🛑 Shutting down processor...")
                break
            except Exception as e:
                print(f"❌ Processing error: {e}")
                time.sleep(1)

if __name__ == "__main__":
    processor = FrameProcessor()
    processor.start_processing()
