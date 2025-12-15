import cv2
from ultralytics import YOLO
import config

class VehicleDetector:
    """
    Handles vehicle detection using the YOLOv8 model.
    """
    def __init__(self, model_path=config.YOLO_MODEL_PATH, device=config.DEVICE, imgsz=config.YOLO_IMGSZ):
        """
        Initializes the YOLOv8 model.
        
        Args:
            model_path (str): Path to the YOLOv8 model file.
            device (str): Device to run inference on ('cuda:0' or 'cpu').
            imgsz (int): Input image size for inference.
        """
        try:
            self.model = YOLO(model_path)
            self.device = device
            self.imgsz = imgsz
            # Warm up the model
            import numpy as np
            dummy = np.zeros((imgsz, imgsz, 3), dtype=np.uint8)
            self.model(dummy, device=device, imgsz=imgsz, verbose=False)
            print(f"YOLO model loaded successfully from {model_path}")
            print(f"Device: {device}, Image size: {imgsz}")
        except Exception as e:
            print(f"Error loading YOLO model: {e}")
            raise

    def detect(self, frame):
        """
        Performs object detection on a single frame.
        
        Args:
            frame (np.ndarray): The input video frame.
            
        Returns:
            list: A list of detections. Each detection is a tuple:
                  ([x1, y1, x2, y2], confidence, class_id)
        """
        # Run YOLO inference with optimizations
        results = self.model(frame, device=self.device, imgsz=self.imgsz, verbose=False, half=True)
        
        detections = []
        
        if results[0].boxes:
            for box in results[0].boxes:
                # Extract data
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                confidence = float(box.conf[0])
                class_id = int(box.cls[0])
                
                # Filter for specified vehicle classes and confidence
                if class_id in config.VEHICLE_CLASS_IDS and confidence > config.CONF_THRESHOLD:
                    detections.append(([x1, y1, x2, y2], confidence, class_id))
                    
        return detections