import cv2
import numpy as np
import config
import os
import time

# Import TensorRT libraries
try:
    import tensorrt as trt
    import pycuda.driver as cuda
    import pycuda.autoinit
except ImportError:
    print("⚠️ TensorRT/PyCUDA not found. GPU inference will fail.")

class VehicleDetector:
    def __init__(self, model_path=None):
        # Ưu tiên dùng đường dẫn từ config nếu không truyền vào
        if model_path is None:
            # Tự động tìm file engine nếu có
            if config.MODEL_FILE and config.MODEL_FILE.endswith('.engine'):
                self.engine_path = config.MODEL_FILE
            elif os.path.exists("yolov8n.engine"):
                self.engine_path = "yolov8n.engine"
            else:
                raise FileNotFoundError("Could not find .engine file in config or current dir")
        else:
            self.engine_path = model_path

        print(f"🚀 Initializing TensorRT Detector with: {self.engine_path}")
        
        # --- LOGIC KHỞI TẠO CỦA BẠN ---
        self.logger = trt.Logger(trt.Logger.WARNING)
        
        with open(self.engine_path, "rb") as f, trt.Runtime(self.logger) as runtime:
            self.engine = runtime.deserialize_cuda_engine(f.read())
        
        if self.engine is None:
            raise RuntimeError("Failed to load TensorRT engine.")

        self.context = self.engine.create_execution_context()
        
        self.inputs = []
        self.outputs = []
        self.allocations = []
        self.input_shape = None
        
        # Setup buffer
        for i in range(self.engine.num_io_tensors):
            name = self.engine.get_tensor_name(i)
            dtype = self.engine.get_tensor_dtype(name)
            shape = self.engine.get_tensor_shape(name)
            
            # Tính size
            vol = 1
            for s in shape:
                vol *= abs(s) if s != -1 else 1 # Handle dynamic shape basic
            
            size = vol * np.dtype(trt.nptype(dtype)).itemsize
            allocation = cuda.mem_alloc(size)
            self.allocations.append(allocation)
            
            binding = {
                'index': i,
                'name': name,
                'dtype': np.dtype(trt.nptype(dtype)),
                'shape': shape,
                'allocation': allocation,
                'size': size
            }
            
            if self.engine.get_tensor_mode(name) == trt.TensorIOMode.INPUT:
                self.inputs.append(binding)
                self.input_shape = shape 
            else:
                self.outputs.append(binding)
                
        # Cache warm-up (optional)
        print("✓ Detector initialized successfully.")

    def preprocess(self, image):
        # Logic preprocess Letterbox của bạn
        input_h = self.input_shape[2] if self.input_shape[2] > 0 else 640
        input_w = self.input_shape[3] if self.input_shape[3] > 0 else 640
        
        h, w = image.shape[:2]
        scale = min(input_w / w, input_h / h)
        nw, nh = int(w * scale), int(h * scale)
        
        image_resized = cv2.resize(image, (nw, nh))
        
        canvas = np.full((input_h, input_w, 3), 114, dtype=np.uint8)
        canvas[(input_h - nh) // 2:(input_h - nh) // 2 + nh, 
               (input_w - nw) // 2:(input_w - nw) // 2 + nw, :] = image_resized
        
        blob = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
        blob = blob.transpose((2, 0, 1)) 
        blob = np.expand_dims(blob, axis=0) 
        blob = blob.astype(np.float32) / 255.0
        
        return blob, scale, (input_w, input_h)

    def detect(self, image):
        """
        Hàm này thay thế cho infer().
        Input: numpy array (ảnh)
        Output: list các detection [([x1, y1, x2, y2], confidence, class_id), ...]
        """
        if image is None: 
            return []

        h_orig, w_orig = image.shape[:2]
        
        # 1. Preprocess
        input_tensor, scale, input_size = self.preprocess(image)
        
        # 2. Copy to GPU
        cuda.memcpy_htod(self.inputs[0]['allocation'], np.ascontiguousarray(input_tensor))
        
        # 3. Set address & Execute Async V3
        for i in range(len(self.inputs)):
            self.context.set_tensor_address(self.inputs[i]['name'], int(self.inputs[i]['allocation']))
        for i in range(len(self.outputs)):
            self.context.set_tensor_address(self.outputs[i]['name'], int(self.outputs[i]['allocation']))

        self.context.execute_async_v3(stream_handle=0)
        
        # 4. Copy back to CPU
        # output_data size calculation depends on implementation, ensure generic enough
        output_binding = self.outputs[0]
        output_data = np.zeros(output_binding['size'] // 4, dtype=np.float32)
        cuda.memcpy_dtoh(output_data, output_binding['allocation'])
        
        # 5. Post-process (Reshape & Transpose)
        # YOLOv8 output: [1, 4+nc, 8400] -> [1, 84, 8400] for COCO
        num_anchors = 8400
        num_channels = output_data.size // num_anchors
        
        output_data = output_data.reshape((num_channels, num_anchors))
        output_data = output_data.transpose() # [8400, 84]
        
        boxes = []
        confidences = []
        class_ids = []
        
        # Duyệt qua các anchor
        for row in output_data:
            classes_scores = row[4:]
            max_score = np.amax(classes_scores)
            
            # Lọc ngưỡng Confidence
            if max_score > config.CONF_THRESHOLD:
                class_id = np.argmax(classes_scores)
                
                # Chỉ lấy các class xe cộ định nghĩa trong config (car, bus, truck...)
                if class_id in config.VEHICLE_CLASS_IDS:
                    x, y, w, h = row[0], row[1], row[2], row[3]
                    
                    left = (x - 0.5 * w)
                    top = (y - 0.5 * h)
                    
                    boxes.append([int(left), int(top), int(w), int(h)])
                    confidences.append(float(max_score))
                    class_ids.append(class_id)
        
        # NMS
        indices = cv2.dnn.NMSBoxes(boxes, confidences, config.CONF_THRESHOLD, 0.45)
        
        final_detections = []
        if len(indices) > 0:
            dw = (input_size[0] - w_orig * scale) / 2
            dh = (input_size[1] - h_orig * scale) / 2
            
            for i in indices.flatten():
                box = boxes[i]
                # Scale lại tọa độ về ảnh gốc
                x = (box[0] - dw) / scale
                y = (box[1] - dh) / scale
                w = box[2] / scale
                h = box[3] / scale
                
                # Clip coordinates để không văng ra ngoài ảnh
                x1 = max(0, int(x))
                y1 = max(0, int(y))
                x2 = min(w_orig, int(x + w))
                y2 = min(h_orig, int(y + h))
                
                # Format trả về cho Tracker: ([x1, y1, x2, y2], conf, class_id)
                final_detections.append(([x1, y1, x2, y2], confidences[i], int(class_ids[i])))

        return final_detections