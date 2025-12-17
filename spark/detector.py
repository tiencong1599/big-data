import cv2
import numpy as np
import onnxruntime as ort
import config

class VehicleDetector:
    """
    Handles vehicle detection using the YOLOv8 ONNX model.
    """
    def __init__(self, model_path='yolov8n.onnx', imgsz=config.YOLO_IMGSZ):
        """
        Initializes the YOLOv8 ONNX model.
        
        Args:
            model_path (str): Path to the YOLOv8 ONNX model file.
            imgsz (int): Input image size for inference.
        """
        try:
            # Create ONNX Runtime session
            providers = ['CPUExecutionProvider']
            if ort.get_device() == 'GPU':
                providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
            
            self.session = ort.InferenceSession(model_path, providers=providers)
            self.imgsz = imgsz
            
            # Get input/output names
            self.input_name = self.session.get_inputs()[0].name
            self.output_names = [output.name for output in self.session.get_outputs()]
            
            print(f"ONNX model loaded successfully from {model_path}")
            print(f"Providers: {providers}, Image size: {imgsz}")
        except Exception as e:
            print(f"Error loading ONNX model: {e}")
            raise
    
    def preprocess(self, frame):
        """
        Preprocess frame for ONNX model input.
        
        Args:
            frame (np.ndarray): Input frame in BGR format
            
        Returns:
            np.ndarray: Preprocessed frame ready for inference
        """
        # Resize to model input size
        img = cv2.resize(frame, (self.imgsz, self.imgsz))
        
        # Convert BGR to RGB
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        # Normalize to [0, 1] and transpose to (1, 3, H, W)
        img = img.astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))
        img = np.expand_dims(img, axis=0)
        
        return img
    
    def postprocess(self, outputs, frame_shape, conf_threshold=config.CONF_THRESHOLD):
        """
        Postprocess ONNX model outputs to extract detections.
        
        Args:
            outputs: Raw model outputs
            frame_shape: Original frame shape (H, W)
            conf_threshold: Confidence threshold
            
        Returns:
            list: Detections in format ([x1, y1, x2, y2], confidence, class_id)
        """
        detections = []
        
        # YOLOv8 output format: (1, 84, 8400) or (1, num_boxes, 84)
        # First 4 values are [x_center, y_center, width, height]
        # Remaining values are class probabilities
        output = outputs[0]
        
        # Transpose if needed: (1, 84, 8400) -> (1, 8400, 84)
        if output.shape[1] == 84:
            output = np.transpose(output, (0, 2, 1))
        
        output = output[0]  # Remove batch dimension
        
        # Get original frame dimensions
        orig_h, orig_w = frame_shape
        
        # Scale factors
        scale_x = orig_w / self.imgsz
        scale_y = orig_h / self.imgsz
        
        for detection in output:
            # Extract box coordinates and class scores
            x_center, y_center, width, height = detection[:4]
            class_scores = detection[4:]
            
            # Get class with highest score
            class_id = np.argmax(class_scores)
            confidence = class_scores[class_id]
            
            # Filter by confidence and vehicle classes
            if confidence > conf_threshold and class_id in config.VEHICLE_CLASS_IDS:
                # Convert from center format to corner format
                x1 = int((x_center - width / 2) * scale_x)
                y1 = int((y_center - height / 2) * scale_y)
                x2 = int((x_center + width / 2) * scale_x)
                y2 = int((y_center + height / 2) * scale_y)
                
                # Clip to frame boundaries
                x1 = max(0, min(x1, orig_w))
                y1 = max(0, min(y1, orig_h))
                x2 = max(0, min(x2, orig_w))
                y2 = max(0, min(y2, orig_h))
                
                detections.append(([x1, y1, x2, y2], float(confidence), int(class_id)))
        
        return detections
    
    def detect(self, frame):
        """
        Performs object detection on a single frame.
        
        Args:
            frame (np.ndarray): The input video frame.
            
        Returns:
            list: A list of detections. Each detection is a tuple:
                  ([x1, y1, x2, y2], confidence, class_id)
        """
        # Preprocess frame
        input_tensor = self.preprocess(frame)
        
        # Run inference
        outputs = self.session.run(self.output_names, {self.input_name: input_tensor})
        
        # Postprocess outputs
        detections = self.postprocess(outputs, frame.shape[:2])
        
        return detections