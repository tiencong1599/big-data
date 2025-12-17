FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for OpenCV
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY spark/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy processor application, config, and ONNX model
COPY spark/*.py ./
COPY yolov8n.onnx ./

# Run Redis real-time processor (no Spark needed)
CMD ["python", "-u", "redis_frame_processor.py"]
