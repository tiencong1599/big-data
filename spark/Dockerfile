# QUAN TRỌNG: Đổi sang bản 'devel' để có nvcc compiler cài PyCUDA
FROM nvidia/cuda:12.1.1-devel-ubuntu22.04

# Cài đặt Python và các thư viện hệ thống
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-dev \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Tạo symlink python -> python3
RUN ln -s /usr/bin/python3 /usr/bin/python

# Thêm đường dẫn CUDA vào biến môi trường (cần cho PyCUDA)
ENV PATH="/usr/local/cuda/bin:${PATH}"
ENV LD_LIBRARY_PATH="/usr/local/cuda/lib64:${LD_LIBRARY_PATH}"

WORKDIR /app

# Copy và cài requirements
COPY spark/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy code
COPY spark/*.py ./

# Copy model (Nên copy cả 2 loại để test)
COPY yolov8n.onnx ./
COPY yolov8n.engine ./

ENV DEVICE=cuda:0

CMD ["python", "-u", "redis_frame_processor.py"]