# Sử dụng Base Image Devel (chứa nvcc compiler)
FROM nvidia/cuda:12.1.1-devel-ubuntu22.04

# Cài đặt Python và các dependency hệ thống
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-dev \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN ln -s /usr/bin/python3 /usr/bin/python

WORKDIR /app

# Copy Requirements và cài đặt
COPY spark/requirements.txt .
# Đảm bảo requirements có: tensorrt, pycuda, onnxruntime-gpu
RUN pip install --no-cache-dir -r requirements.txt

RUN pip install --no-cache-dir \
    torch==2.1.2+cpu \
    torchvision==0.16.2+cpu \
    --index-url https://download.pytorch.org/whl/cpu

# Copy source code
COPY spark/*.py ./

# Copy file converter vừa tạo
COPY spark/converter.py ./

# Copy ONNX model
COPY spark/yolov8s.onnx ./

# --- SETUP TỰ ĐỘNG HÓA ---
# Copy entrypoint script
COPY spark/entrypoint.sh ./
# Cấp quyền thực thi (quan trọng!)
RUN chmod +x entrypoint.sh

ENV DEVICE=cuda:0

# Set Entrypoint là script bash
ENTRYPOINT ["./entrypoint.sh"]

# CMD là lệnh chạy app chính (sẽ được entrypoint gọi sau khi check xong)
CMD ["python", "-u", "redis_frame_processor.py"]