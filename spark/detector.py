import cv2
import numpy as np
import config
import time
import os

# Import TensorRT libraries an toàn
try:
    import tensorrt as trt
    import pycuda.driver as cuda
    import pycuda.autoinit
except ImportError:
    print("⚠️ TensorRT/PyCUDA not found. Ensure you are running inside the Docker container.")

class VehicleDetector:
    def __init__(self, model_name='yolov8n', imgsz=config.YOLO_IMGSZ):
        self.imgsz = imgsz
        self.conf_threshold = config.CONF_THRESHOLD
        
        # Tự động tìm file model
        engine_path = f"{model_name}.engine"
        onnx_path = f"{model_name}.onnx"
        
        print(f"🔄 Initializing Detector...")

        if os.path.exists(engine_path):
            print(f"🚀 Found Optimized Engine: {engine_path}")
            self.model_path = engine_path
            self.backend = 'tensorrt'
            self._init_tensorrt(engine_path)
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
        print("  -> Loading TensorRT Engine (v10+ compatible)...")
        try:
            self.trt_logger = trt.Logger(trt.Logger.WARNING)
            runtime = trt.Runtime(self.trt_logger)
            
            with open(model_path, 'rb') as f:
                engine_data = f.read()
            
            self.engine = runtime.deserialize_cuda_engine(engine_data)
            self.context = self.engine.create_execution_context()
            
            self.inputs = []
            self.outputs = []
            self.stream = cuda.Stream() # Tạo luồng xử lý GPU
            
            # --- LOGIC XỬ LÝ MEMORY (HỖ TRỢ TRT 10.x VÀ 8.x) ---
            
            # Cách xác định số lượng tensors tùy version
            if hasattr(self.engine, 'num_io_tensors'):
                num_bindings = self.engine.num_io_tensors
                is_trt_10 = True
            else:
                num_bindings = self.engine.num_bindings
                is_trt_10 = False

            for i in range(num_bindings):
                if is_trt_10:
                    name = self.engine.get_tensor_name(i)
                    mode = self.engine.get_tensor_mode(name)
                    is_input = (mode == trt.TensorIOMode.INPUT)
                    shape = self.engine.get_tensor_shape(name)
                    # FIX LỖI TYPE: Bọc vào np.dtype
                    dtype = np.dtype(trt.nptype(self.engine.get_tensor_dtype(name)))
                else:
                    name = self.engine.get_binding_name(i)
                    is_input = self.engine.binding_is_input(i)
                    shape = self.engine.get_binding_shape(i)
                    # FIX LỖI TYPE
                    dtype = np.dtype(trt.nptype(self.engine.get_binding_dtype(i)))

                # Xử lý Dynamic Shape (nếu có -1)
                if -1 in shape:
                    print(f"  ⚠️ Warning: Dynamic shape found {shape}, forcing batch=1")
                    lst = list(shape)
                    if lst[0] == -1: lst[0] = 1
                    shape = tuple(lst)

                # Tính kích thước bộ nhớ cần cấp phát
                size = trt.volume(shape) * dtype.itemsize
                
                # Cấp phát bộ nhớ trên GPU
                device_mem = cuda.mem_alloc(size)
                
                # Tạo binding dictionary
                binding = {
                    'name': name,
                    'index': i,
                    'device': device_mem, # Pointer GPU
                    'host': None,         # Pointer CPU (sẽ tạo cho output)
                    'shape': shape,
                    'dtype': dtype
                }

                if is_input:
                    self.inputs.append(binding)
                    # TRT 10 bắt buộc set address
                    if is_trt_10: self.context.set_tensor_address(name, int(device_mem))
                else:
                    # Output cần bộ nhớ đệm ở CPU (Host) để nhận kết quả về
                    binding['host'] = cuda.pagelocked_empty(trt.volume(shape), dtype)
                    self.outputs.append(binding)
                    if is_trt_10: self.context.set_tensor_address(name, int(device_mem))

            print("  ✓ TensorRT Engine Loaded & Memory Allocated.")
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise RuntimeError(f"TensorRT Init Failed: {e}")

    def preprocess(self, frame):
        # Resize và chuẩn hóa ảnh cho YOLO
        img = cv2.resize(frame, (self.imgsz, self.imgsz))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1)) # HWC -> CHW
        img = np.expand_dims(img, axis=0)  # Thêm batch dimension -> (1, 3, 640, 640)
        return np.ascontiguousarray(img)

    def detect(self, frame):
        # 1. Preprocess
        input_tensor = self.preprocess(frame)
        
        # 2. Inference
        if self.backend == 'onnx':
            outputs = self.session.run(self.output_names, {self.input_name: input_tensor})
        
        elif self.backend == 'tensorrt':
            # --- FIX LỖI INPUT BUFFER TẠI ĐÂY ---
            
            # Lấy địa chỉ bộ nhớ GPU của input đầu tiên
            input_mem = self.inputs[0]['device']
            
            # Copy dữ liệu từ CPU (input_tensor) lên GPU (input_mem)
            cuda.memcpy_htod_async(input_mem, input_tensor, self.stream)
            
            # Thực thi mô hình (Execute)
            self.context.execute_async_v3(stream_handle=self.stream.handle)
            
            # Copy kết quả từ GPU (device) về CPU (host)
            for out in self.outputs:
                cuda.memcpy_dtoh_async(out['host'], out['device'], self.stream)
            
            # Đồng bộ hóa (Chờ GPU chạy xong)
            self.stream.synchronize()
            
            # Lấy kết quả ra list
            outputs = [out['host'].reshape(out['shape']) for out in self.outputs]

        # 3. Postprocess
        return self.postprocess(outputs, frame.shape[:2])

    def postprocess(self, outputs, frame_shape):
        detections = []
        # Output của YOLOv8 thường là [1, 84, 8400] -> cần transpose thành [1, 8400, 84]
        output = outputs[0]
        if output.shape[1] == 84: 
            output = np.transpose(output, (0, 2, 1))
        
        output = output[0] # Lấy batch đầu tiên
        
        orig_h, orig_w = frame_shape
        scale_x = orig_w / self.imgsz
        scale_y = orig_h / self.imgsz
        
        # Format output: [x, y, w, h, class_probs...]
        classes_scores = output[:, 4:]
        class_ids = np.argmax(classes_scores, axis=1)
        confidences = np.max(classes_scores, axis=1)
        
        # Lọc ngưỡng tự tin (Confidence Threshold)
        mask = (confidences > self.conf_threshold) & (np.isin(class_ids, config.VEHICLE_CLASS_IDS))
        
        filtered_output = output[mask]
        filtered_confidences = confidences[mask]
        filtered_class_ids = class_ids[mask]
        
        for i, detection in enumerate(filtered_output):
            x_center, y_center, width, height = detection[:4]
            
            # Chuyển đổi tọa độ về ảnh gốc
            x1 = int((x_center - width / 2) * scale_x)
            y1 = int((y_center - height / 2) * scale_y)
            x2 = int((x_center + width / 2) * scale_x)
            y2 = int((y_center + height / 2) * scale_y)
            
            # Clip để không văng ra ngoài khung hình
            x1 = max(0, min(x1, orig_w))
            y1 = max(0, min(y1, orig_h))
            x2 = max(0, min(x2, orig_w))
            y2 = max(0, min(y2, orig_h))
            
            detections.append(([x1, y1, x2, y2], float(filtered_confidences[i]), int(filtered_class_ids[i])))
        
        return detections