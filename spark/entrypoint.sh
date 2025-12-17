#!/bin/bash
# file: entrypoint.sh

# Dừng lại ngay nếu có lỗi
set -e

ONNX_MODEL="yolov8n.onnx"
ENGINE_MODEL="yolov8n.engine"

echo "============================================="
echo "   CONTAINER STARTUP CHECK"
echo "============================================="

# 1. Kiểm tra xem file Engine đã tồn tại chưa
if [ -f "$ENGINE_MODEL" ]; then
    echo "✓ Found existing TensorRT engine: $ENGINE_MODEL"
else
    echo "⚠️ TensorRT engine not found. Starting conversion..."
    
    # Kiểm tra file ONNX
    if [ ! -f "$ONNX_MODEL" ]; then
        echo "❌ Error: $ONNX_MODEL not found! Cannot build engine."
        exit 1
    fi
    
    # Gọi python script để convert
    python3 converter.py "$ONNX_MODEL" "$ENGINE_MODEL"
fi

echo "============================================="
echo "🚀 STARTING MAIN APPLICATION"
echo "============================================="

# Chạy lệnh được truyền vào từ CMD của Dockerfile
exec "$@"