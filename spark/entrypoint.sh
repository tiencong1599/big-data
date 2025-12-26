#!/bin/bash
set -e

ONNX_MODEL="yolov8n.onnx"
ENGINE_MODEL="yolov8n.engine"

echo "============================================="
echo "   CONTAINER DEBUG INFO"
echo "============================================="
echo "Current Directory: $(pwd)"
echo "List of files in current directory:"
ls -la
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
        echo "❌ Error: $ONNX_MODEL not found in $(pwd)!"
        # Đừng exit ngay, hãy sleep để bạn kịp đọc log nếu nó restart quá nhanh
        sleep 10
        exit 1
    fi

    echo "============================================="
    echo "🚀 STARTING CONVERTING MODEL APPLICATION"
    echo "============================================="
    # Gọi python script để convert (Thêm -u để log hiện ra ngay lập tức)
    python3 -u converter.py "$ONNX_MODEL" "$ENGINE_MODEL"
fi

echo "============================================="
echo "🚀 STARTING MAIN APPLICATION"
echo "============================================="

exec "$@"