import cv2
import numpy as np
import os
import config

class VehicleDetector:
    """
    Handles vehicle detection using YOLOv8 with TensorRT or ONNX backend.
    """
    def __init__(self, model_path='yolov8n.engine', imgsz=config.YOLO_IMGSZ):
        """
        Initializes the YOLOv8 model with TensorRT or ONNX backend.
        
        Args:
            model_path (str): Path to the model file (.engine or .onnx)
            imgsz (int): Input image size for inference.
        """
        self.imgsz = imgsz
        self.model_path = model_path
        
        # Determine backend based on file extension
        if model_path.endswith('.engine'):
            self._init_tensorrt(model_path)
        elif model_path.endswith('.onnx'):
            self._init_onnx(model_path)
        else:
            raise ValueError(f"Unsupported model format: {model_path}")
    
    def _init_tensorrt(self, model_path):
        """Initialize TensorRT engine for GPU inference"""
        try:
            import tensorrt as trt
            import pycuda.driver as cuda
            import pycuda.autoinit  # Automatic CUDA context management
            
            self.backend = 'tensorrt'
            print(f"Loading TensorRT engine: {model_path}")
            
            # Create TensorRT logger and runtime
            self.trt_logger = trt.Logger(trt.Logger.WARNING)
            runtime = trt.Runtime(self.trt_logger)
            
            # Load serialized engine
            with open(model_path, 'rb') as f:
                engine_data = f.read()
            
            self.engine = runtime.deserialize_cuda_engine(engine_data)
            if self.engine is None:
                raise RuntimeError("Failed to deserialize TensorRT engine")
            
            self.context = self.engine.create_execution_context()
            
            # Get input/output binding information
            self.input_name = None
            self.output_names = []
            self.bindings = []
            self.output_buffers = []
            
            for i in range(self.engine.num_bindings):
                name = self.engine.get_binding_name(i)
                dtype = trt.nptype(self.engine.get_binding_dtype(i))
                shape = self.engine.get_binding_shape(i)
                size = trt.volume(shape)
                
                # Allocate device memory
                device_mem = cuda.mem_alloc(size * dtype.itemsize)
                self.bindings.append(int(device_mem))
                
                if self.engine.binding_is_input(i):
                    self.input_name = name
                    self.input_shape = shape
                    self.input_dtype = dtype
                    self.input_buffer = device_mem
                else:
                    self.output_names.append(name)
                    # Allocate host memory for output
                    host_mem = cuda.pagelocked_empty(size, dtype)
                    self.output_buffers.append((device_mem, host_mem, shape))
            
            print(f"✓ TensorRT engine loaded: {model_path}")
            print(f"  Input: {self.input_name} {self.input_shape}")
            print(f"  Outputs: {self.output_names}")
            
        except ImportError as e:
            raise ImportError(
                "TensorRT dependencies not installed. "
                "Install: pip install tensorrt pycuda"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Failed to initialize TensorRT engine: {e}") from e
    
    def _init_onnx(self, model_path):
        """Initialize ONNX Runtime for CPU/GPU inference"""
        try:
            import onnxruntime as ort
            
            self.backend = 'onnx'
            print(f"Loading ONNX model: {model_path}")
            
            # Configure execution providers
            providers = ['CPUExecutionProvider']
            if ort.get_device() == 'GPU':
                providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
            
            self.session = ort.InferenceSession(model_path, providers=providers)
            self.input_name = self.session.get_inputs()[0].name
            self.output_names = [output.name for output in self.session.get_outputs()]
            
            print(f"✓ ONNX model loaded: {model_path}")
            print(f"  Providers: {providers}")
            
        except ImportError as e:
            raise ImportError("ONNX Runtime not installed. Install: pip install onnxruntime-gpu") from e
    
    def preprocess(self, frame):
        """
        Preprocess frame for model input.
        
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
        
        # Ensure contiguous array
        img = np.ascontiguousarray(img)
        
        return img
    
    def _inference_tensorrt(self, input_tensor):
        """Run inference using TensorRT"""
        import pycuda.driver as cuda
        
        # Copy input to device
        cuda.memcpy_htod(self.input_buffer, input_tensor)
        
        # Run inference
        self.context.execute_v2(bindings=self.bindings)
        
        # Copy outputs to host
        outputs = []
        for device_mem, host_mem, shape in self.output_buffers:
            cuda.memcpy_dtoh(host_mem, device_mem)
            outputs.append(host_mem.reshape(shape))
        
        return outputs
    
    def _inference_onnx(self, input_tensor):
        """Run inference using ONNX Runtime"""
        outputs = self.session.run(self.output_names, {self.input_name: input_tensor})
        return outputs
    
    def postprocess(self, outputs, frame_shape, conf_threshold=config.CONF_THRESHOLD):
        """
        Postprocess model outputs to extract detections.
        
        Args:
            outputs: Raw model outputs
            frame_shape: Original frame shape (H, W)
            conf_threshold: Confidence threshold
            
        Returns:
            list: Detections in format ([x1, y1, x2, y2], confidence, class_id)
        """
        detections = []
        
        # YOLOv8 output format: (1, 84, 8400) or (1, num_boxes, 84)
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
        
        # Run inference based on backend
        if self.backend == 'tensorrt':
            outputs = self._inference_tensorrt(input_tensor)
        else:  # onnx
            outputs = self._inference_onnx(input_tensor)
        
        # Postprocess outputs
        detections = self.postprocess(outputs, frame.shape[:2])
        
        return detections