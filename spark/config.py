import os
import json
import numpy as np

# --- DEVICE CONFIGURATION ---

# Model file path - automatically detect .engine or .onnx
# Priority: .engine (TensorRT GPU) > .onnx (ONNX Runtime)
MODEL_FILE = None
DEVICE = os.getenv('DEVICE', 'cuda:0')  # 'cuda:0' for GPU, 'cpu' for CPU

# Auto-detect available model file
if os.path.exists('yolov8s.engine'):
    MODEL_FILE = 'yolov8s.engine'
    print("✓ Found TensorRT engine model (GPU acceleration)")
elif os.path.exists('yolov8s.onnx'):
    MODEL_FILE = 'yolov8s.onnx'
    print("✓ Found ONNX model (CPU/GPU)")
else:
    raise FileNotFoundError("No model file found! Place yolov8s.engine or yolov8s.onnx in spark/ directory")

# YOLO Model Path
YOLO_MODEL_PATH = MODEL_FILE

# YOLO inference image size (must match model export size)
YOLO_IMGSZ = 640

# --- REDIS CONFIGURATION ---

REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_INPUT_STREAM = os.getenv('REDIS_INPUT_STREAM', 'video-frames')
REDIS_OUTPUT_STREAM = os.getenv('REDIS_OUTPUT_STREAM', 'processed-frames')

# --- CALIBRATION DATA ---

# Camera Matrix (K) - from calibration
CAMERA_MATRIX_K = None

# Homography Matrix (H) - from calibration
HOMOGRAPHY_MATRIX_H = None

# ROI Polygon
ROI_POLYGON = []

# Load calibration files if available
if os.path.exists('camera_calibration.json'):
    with open('camera_calibration.json', 'r') as f:
        calib_data = json.load(f)
        CAMERA_MATRIX_K = np.array(calib_data['camera_matrix_K'], dtype=np.float32)
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

# --- VIDEO PROCESSING CONFIG ---

# Video FPS
VIDEO_FPS = 30.0

# Frame skip: Process every Nth frame (1 = all frames, 2 = every other frame)
FRAME_SKIP = 2

# Default video FPS when not provided
DEFAULT_VIDEO_FPS = 30

# --- DETECTION & TRACKING CONFIG ---

# Vehicle Classes to Detect (COCO class IDs)
# 0: 'car', 1: 'bus', 2: 'truck', 3: 'motobike'
VEHICLE_CLASS_IDS = [0, 1, 2, 3]

# Detection Confidence Threshold
CONF_THRESHOLD = 0.4

# --- SPEED ESTIMATION CONFIG ---

# Speed conversion factor (m/s to km/h: 3.6, m/s to mph: 2.23694)
SPEED_CONVERSION_FACTOR = 3.6
SPEED_UNIT = "km/h"

# Minimum track length for speed calculation
MIN_TRACK_LENGTH = 5

# --- TRACKER CONFIG ---

TRACKER_MAX_AGE = 30
TRACKER_N_INIT = 3
TRACKER_MAX_IOU_DISTANCE = 0.7

print(f"Configuration loaded: Model={YOLO_MODEL_PATH}, Device={DEVICE}")