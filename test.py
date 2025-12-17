import cv2
import tensorrt as trt
import pycuda.driver as cuda
import pycuda.autoinit
import numpy as np
from ultralytics import YOLO

import tensorrt as trt
import os

def build_raw_engine(onnx_file_path, engine_file_path):
    logger = trt.Logger(trt.Logger.WARNING)
    builder = trt.Builder(logger)
    
    # Tạo network với Explicit Batch (bắt buộc cho YOLOv8)
    network = builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH))
    parser = trt.OnnxParser(network, logger)
    config = builder.create_builder_config()

    print(f"Đang đọc file ONNX: {onnx_file_path}...")
    with open(onnx_file_path, 'rb') as model:
        if not parser.parse(model.read()):
            print("LỖI: Không thể parse file ONNX.")
            for error in range(parser.num_errors):
                print(parser.get_error(error))
            return None

    # Cấu hình bộ nhớ workspace (cho phép TRT dùng tối đa RAM để tối ưu)
    # TensorRT 10.x quản lý bộ nhớ tự động tốt hơn, nhưng set limit vẫn an toàn
    config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 2 * (1 << 30)) # 2GB

    # Bật chế độ FP16 nếu GPU hỗ trợ (GTX 1650 Ti có hỗ trợ)
    if builder.platform_has_fast_fp16:
        print("Đang bật chế độ FP16...")
        config.set_flag(trt.BuilderFlag.FP16)

    print("Đang build Engine (Raw)... Sẽ mất vài phút...")
    serialized_engine = builder.build_serialized_network(network, config)

    if serialized_engine:
        with open(engine_file_path, "wb") as f:
            f.write(serialized_engine)
        print(f"Thành công! Engine sạch đã lưu tại: {engine_file_path}")
    else:
        print("Build thất bại.")

class YOLOv8TRT:
    def __init__(self, engine_path):
        # Khởi tạo Logger
        self.logger = trt.Logger(trt.Logger.WARNING)
        
        # Load Engine
        with open(engine_path, "rb") as f, trt.Runtime(self.logger) as runtime:
            self.engine = runtime.deserialize_cuda_engine(f.read())
        
        self.context = self.engine.create_execution_context()
        
        # Lấy thông tin input/output
        self.inputs = []
        self.outputs = []
        self.allocations = []
        
        for i in range(self.engine.num_io_tensors):
            name = self.engine.get_tensor_name(i)
            dtype = self.engine.get_tensor_dtype(name)
            shape = self.engine.get_tensor_shape(name)
            
            # Tính toán kích thước bộ nhớ
            size = trt.volume(shape) * np.dtype(trt.nptype(dtype)).itemsize
            
            # Cấp phát bộ nhớ trên GPU
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
                self.input_shape = shape # (1, 3, 640, 640)
            else:
                self.outputs.append(binding)

    def preprocess(self, image):
        # Resize và padding (Letterbox) để giữ tỉ lệ ảnh
        h, w = image.shape[:2]
        input_h, input_w = self.input_shape[2], self.input_shape[3]
        scale = min(input_w / w, input_h / h)
        nw, nh = int(w * scale), int(h * scale)
        
        image_resized = cv2.resize(image, (nw, nh))
        
        # Tạo canvas màu xám
        canvas = np.full((input_h, input_w, 3), 114, dtype=np.uint8)
        canvas[(input_h - nh) // 2:(input_h - nh) // 2 + nh, 
               (input_w - nw) // 2:(input_w - nw) // 2 + nw, :] = image_resized
        
        # Chuẩn hóa: BGR -> RGB, /255.0, HWC -> CHW
        blob = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
        blob = blob.transpose((2, 0, 1)) # CHW
        blob = np.expand_dims(blob, axis=0) # Batch dimension
        blob = blob.astype(np.float32) / 255.0
        return blob, scale, (input_w, input_h)

    def infer(self, image_path, conf_thres=0.5, iou_thres=0.5):
        # 1. Đọc và tiền xử lý
        original_image = cv2.imread(image_path)
        input_tensor, scale, input_size = self.preprocess(original_image)
        
        # 2. Copy dữ liệu xuống GPU
        cuda.memcpy_htod(self.inputs[0]['allocation'], np.ascontiguousarray(input_tensor))
        
        # 3. Chạy Inference (Execute Async V2 là chuẩn cho TRT mới)
        # Set tensor address cho TRT 10.x
        for i in range(len(self.inputs)):
            self.context.set_tensor_address(self.inputs[i]['name'], int(self.inputs[i]['allocation']))
        for i in range(len(self.outputs)):
            self.context.set_tensor_address(self.outputs[i]['name'], int(self.outputs[i]['allocation']))

        self.context.execute_async_v3(stream_handle=0) # Dùng V3 cho TRT 8.6+ và 10.x
        
        # 4. Copy kết quả về CPU
        output_data = np.zeros(self.outputs[0]['shape'], dtype=self.outputs[0]['dtype'])
        cuda.memcpy_dtoh(output_data, self.outputs[0]['allocation'])
        
        # 5. Hậu xử lý (Post-processing)
        # Output YOLOv8 thường là [1, 84, 8400] (gồm 4 box coords + 80 classes)
        output_data = np.squeeze(output_data) # [84, 8400]
        output_data = output_data.transpose() # [8400, 84]
        
        boxes = []
        confidences = []
        class_ids = []
        
        h_orig, w_orig = original_image.shape[:2]
        
        # Duyệt qua các anchor
        for row in output_data:
            classes_scores = row[4:]
            max_score = np.amax(classes_scores)
            
            if max_score > conf_thres:
                class_id = np.argmax(classes_scores)
                x, y, w, h = row[0], row[1], row[2], row[3]
                
                # Giải mã Box (từ center_x, center_y, w, h sang left, top, w, h)
                left = (x - 0.5 * w)
                top = (y - 0.5 * h)
                
                boxes.append([int(left), int(top), int(w), int(h)])
                confidences.append(float(max_score))
                class_ids.append(class_id)
        
        # NMS (Non-Maximum Suppression) để loại bỏ box trùng
        indices = cv2.dnn.NMSBoxes(boxes, confidences, conf_thres, iou_thres)
        
        # Vẽ kết quả
        if len(indices) > 0:
            # Scale lại tọa độ box về kích thước ảnh gốc
            # Cần tính toán offset padding lúc preprocess để scale chính xác
            dw = (input_size[0] - w_orig * scale) / 2
            dh = (input_size[1] - h_orig * scale) / 2
            
            for i in indices.flatten():
                box = boxes[i]
                x = (box[0] - dw) / scale
                y = (box[1] - dh) / scale
                w = box[2] / scale
                h = box[3] / scale
                
                x, y, w, h = int(x), int(y), int(w), int(h)
                
                color = (0, 255, 0)
                cv2.rectangle(original_image, (x, y), (x + w, y + h), color, 2)
                label = f"ID:{class_ids[i]} {confidences[i]:.2f}"
                cv2.putText(original_image, label, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        return original_image

# --- Chạy hàm này ---
# Đảm bảo file onnx nằm đúng đường dẫn (theo log của bạn là thư mục hiện tại)
# build_raw_engine("yolov8s.onnx", "yolov8s_clean.engine")

# print("Đã xong! File yolov8s.engine mới đã được tạo.")

engine_file = "yolov8s_clean.engine"
img_file = "F:\\dataset\\obj\\obj\\600002293.png" # Thay bằng ảnh của bạn

trt_detector = YOLOv8TRT(engine_file)
result_img = trt_detector.infer(img_file)

cv2.imshow("Result", result_img)
cv2.waitKey(0)
cv2.destroyAllWindows()