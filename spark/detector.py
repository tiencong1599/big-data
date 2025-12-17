import cv2
import numpy as np
import os
import config

class VehicleDetector:
    def __init__(self, model_name='yolov8n', imgsz=config.YOLO_IMGSZ):
        # Tự động chọn file tốt nhất
        engine_path = f"{model_name}.engine"
        onnx_path = f"{model_name}.onnx"
        
        self.imgsz = imgsz
        
        # Ưu tiên load Engine trước
        if os.path.exists(engine_path):
            print(f"🚀 Found Optimized Engine: {engine_path}")
            self.model_path = engine_path
            self.backend = 'tensorrt'
            self._init_tensorrt(engine_path)
        
        # Nếu không có engine thì dùng ONNX
        elif os.path.exists(onnx_path):
            print(f"⚠️ Engine not found, falling back to ONNX: {onnx_path}")
            self.model_path = onnx_path
            self.backend = 'onnx'
            self._init_onnx(onnx_path)
        else:
            raise FileNotFoundError(f"Could not find {engine_path} or {onnx_path}")

    def _init_onnx(self, model_path):
        import onnxruntime as ort
        print("  -> Loading ONNX Runtime...")
        providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        self.session = ort.InferenceSession(model_path, sess_options=opts, providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [output.name for output in self.session.get_outputs()]
        print(f"  ✓ ONNX Loaded. Provider: {self.session.get_providers()[0]}")

    def _init_tensorrt(self, model_path):
        print("  -> Loading TensorRT Engine...")
        try:
            import tensorrt as trt
            import pycuda.driver as cuda
            import pycuda.autoinit  # Tự động khởi tạo CUDA Context
            
            self.trt_logger = trt.Logger(trt.Logger.WARNING)
            runtime = trt.Runtime(self.trt_logger)
            
            with open(model_path, 'rb') as f:
                engine_data = f.read()
            
            self.engine = runtime.deserialize_cuda_engine(engine_data)
            self.context = self.engine.create_execution_context()
            
            # Cấp phát bộ nhớ
            self.inputs, self.outputs, self.bindings = [], [], []
            self.stream = cuda.Stream()
            
            for i in range(self.engine.num_bindings):
                tensor_name = self.engine.get_binding_name(i)
                dtype = trt.nptype(self.engine.get_binding_dtype(i))
                shape = self.engine.get_binding_shape(i)
                
                # Xử lý dynamic shape nếu cần (với YOLO thường là fix cứng)
                if shape[0] == -1: shape = (1,) + shape[1:]
                
                size = trt.volume(shape) * dtype.itemsize
                
                # Cấp phát bộ nhớ trên GPU
                device_mem = cuda.mem_alloc(size)
                self.bindings.append(int(device_mem))
                
                if self.engine.binding_is_input(i):
                    self.inputs.append({'host': None, 'device': device_mem, 'shape': shape, 'dtype': dtype})
                else:
                    host_mem = cuda.pagelocked_empty(trt.volume(shape), dtype)
                    self.outputs.append({'host': host_mem, 'device': device_mem, 'shape': shape})
            
            print("  ✓ TensorRT Engine Loaded successfully.")
            
        except ImportError:
            raise ImportError("Missing libraries for TensorRT. Please install 'tensorrt' and 'pycuda'.")
        except Exception as e:
            raise RuntimeError(f"TensorRT Init Failed: {e}")

    def preprocess(self, frame):
        img = cv2.resize(frame, (self.imgsz, self.imgsz))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))
        img = np.expand_dims(img, axis=0)
        return np.ascontiguousarray(img)

    def detect(self, frame):
        input_tensor = self.preprocess(frame)
        
        if self.backend == 'onnx':
            outputs = self.session.run(self.output_names, {self.input_name: input_tensor})
        
        elif self.backend == 'tensorrt':
            import pycuda.driver as cuda
            # Copy input to device
            cuda.memcpy_htod_async(self.inputs[0]['device'], input_tensor, self.stream)
            # Run inference
            self.context.execute_async_v2(bindings=self.bindings, stream_handle=self.stream.handle)
            # Copy output back
            for out in self.outputs:
                cuda.memcpy_dtoh_async(out['host'], out['device'], self.stream)
            self.stream.synchronize()
            outputs = [out['host'].reshape(out['shape']) for out in self.outputs]

        return self.postprocess(outputs, frame.shape[:2])
    
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