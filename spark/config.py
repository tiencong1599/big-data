import numpy as np
import json
import os
# --- CRITICAL CONFIGURATION ---
# These values MUST be replaced with your own calibration results.
# You can get these by running the `calibrate.py` utility.

# 1. Camera Intrinsic Matrix (K)
# This is a 3x3 matrix specific to your camera lens and sensor.
# Format: np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]])
CAMERA_MATRIX_K = np.array([
    [1000.0, 0.0, 640.0],  # fx, 0, cx
    [0.0, 1000.0, 360.0], # 0, fy, cy
    [0.0, 0.0, 1.0]    # 0, 0, 1
], dtype=np.float32)

# 2. Image-to-World Homography Matrix (H)
# This 3x3 matrix maps 2D pixel coordinates (from the image) to 3D
# real-world coordinates (on the ground plane, e.g., in meters).
# This is specific to your camera's *position and angle*.
HOMOGRAPHY_MATRIX_H = np.array([
        [
            0.08383036974498041,
            0.047154582981551424,
            -79.4187965371508
        ],
        [
            -0.0013170073950060954,
            0.24035384958861367,
            -65.77661733618478
        ],
        [
            0.0005355704990241491,
            0.009876815124886492,
            1.0
        ]
    ], dtype=np.float32)


ROI_POLYGON = None

# --- Load calibration data from JSON files if they exist ---
if os.path.exists('camera_calibration.json'):
    with open('camera_calibration.json', 'r') as f:
        camera_data = json.load(f)
        CAMERA_MATRIX_K = np.array(camera_data['camera_matrix_K'], dtype=np.float32)
        print("Loaded camera matrix from camera_calibration.json")

if os.path.exists('homography_config.json'):
    with open('homography_config.json', 'r') as f:
        homography_data = json.load(f)
        HOMOGRAPHY_MATRIX_H = np.array(homography_data['homography_matrix_H'], dtype=np.float32)
        print("Loaded homography matrix from homography_config.json")

if os.path.exists('roi_config.json'):
    with open('roi_config.json', 'r') as f:
        roi_data = json.load(f)
        ROI_POLYGON = roi_data['roi_polygon']
        print(f"Loaded ROI polygon from roi_config.json: {len(ROI_POLYGON)} points")
# 3. Video FPS
# Set this to the FPS of your input video.
# This is crucial for accurate speed calculation (distance / time).
VIDEO_FPS = 30.0

# --- PERFORMANCE OPTIMIZATION ---

# Frame skip: Process every Nth frame (1 = process all frames, 2 = process every other frame)
FRAME_SKIP = 2

# YOLO inference image size (smaller = faster, larger = more accurate)
# Default: 640. Options: 320, 416, 512, 640, 1280
YOLO_IMGSZ = 416

# Device for inference ('cuda:0' for GPU, 'cpu' for CPU)
# GPU is 10-20x faster than CPU
DEVICE = os.getenv('DEVICE', 'cpu')  # Use CPU by default in containers

CONFIDENCE_THRESHOLD = 0.5

# Default video FPS when not provided
DEFAULT_VIDEO_FPS = 30

# --- DETECTION & TRACKING CONFIG ---

# 4. YOLO Model
# 'yolov8n.pt' is small and fast.
# 'yolov8m.pt' is a good balance of speed and accuracy.
# 'yolov8l.pt' is slower but more accurate.
YOLO_MODEL_PATH = 'yolov8n.pt'

# 5. Vehicle Classes to Detect
# COCO class IDs for common vehicles:
# 2: 'car', 3: 'motorcycle', 5: 'bus', 7: 'truck'
VEHICLE_CLASS_IDS = [2, 3, 5, 7]

# 6. Detection Confidence Threshold
# Only detections with confidence > this value will be considered.
CONF_THRESHOLD = 0.4

# 7. Speed Unit Conversion
# Speed is calculated in meters/second (m/s) by default.
# To convert to km/h: 3.6
# To convert to mph: 2.23694
SPEED_CONVERSION_FACTOR = 3.6
SPEED_UNIT = "km/h"

# Minimum track length for speed calculation
MIN_TRACK_LENGTH = 5

# --- DeepSORT TRACKER CONFIG ---

TRACKER_MAX_AGE = 30
TRACKER_N_INIT = 3
TRACKER_MAX_IOU_DISTANCE = 0.7