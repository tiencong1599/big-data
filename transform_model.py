from ultralytics import YOLO
import torch
import sys

def check_gpu_status():
    """Kiểm tra chi tiết trạng thái GPU và CUDA"""
    print("=" * 60)
    print("🔍 KIỂM TRA GPU & CUDA")
    print("=" * 60)
    
    # Kiểm tra CUDA availability
    cuda_available = torch.cuda.is_available()
    print(f"PyTorch CUDA available: {cuda_available}")
    
    if cuda_available:
        print(f"✅ GPU được phát hiện: {torch.cuda.get_device_name(0)}")
        print(f"   CUDA Version: {torch.version.cuda}")
        print(f"   GPU Count: {torch.cuda.device_count()}")
        print(f"   Current Device: {torch.cuda.current_device()}")
        print(f"   GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB")
    else:
        print("❌ Không tìm thấy GPU hoặc CUDA chưa được cài đúng cách")
        print("\n📋 Hướng dẫn khắc phục:")
        print("1. Kiểm tra bạn có GPU NVIDIA hay không")
        print("2. Cài NVIDIA Driver mới nhất")
        print("3. Cài CUDA Toolkit: https://developer.nvidia.com/cuda-downloads")
        print("4. Cài PyTorch với CUDA support:")
        print("   pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118")
        print("\n⚠️ Lưu ý: Bạn vẫn có thể export ONNX và chạy trên CPU!")
    
    print("=" * 60)
    return cuda_available

def export_to_tensorrt(model, model_path):
    """Export model sang TensorRT format (.engine)"""
    print("\n🚀 EXPORT TO TENSORRT (.engine)")
    print("-" * 60)
    print("⏳ Đang export sang TensorRT (có thể mất 2-5 phút)...")
    
    try:
        model.export(
            format='engine', 
            device=0,           # GPU device
            half=True,          # FP16 precision (faster)
            simplify=True,      # Simplify model
            workspace=4,        # Max workspace size (GB)
            verbose=False
        )
        engine_path = model_path.replace('.pt', '.engine')
        print(f"✅ TensorRT export SUCCESS: {engine_path}")
        print("   → Sử dụng để inference cực nhanh trên GPU")
        return True
    except Exception as e:
        print(f"❌ TensorRT export FAILED: {e}")
        print("   Kiểm tra: pip install nvidia-tensorrt")
        return False

def export_to_onnx(model, model_path, use_gpu=False):
    """Export model sang ONNX format"""
    print("\n🚀 EXPORT TO ONNX (.onnx)")
    print("-" * 60)
    
    if use_gpu:
        print("⏳ Đang export ONNX (GPU-optimized)...")
    else:
        print("⏳ Đang export ONNX (CPU-compatible)...")
    
    try:
        model.export(
            format='onnx',
            simplify=True,      # Optimize model graph
            dynamic=False,      # Static shape for better performance
            opset=12,          # ONNX opset version
            verbose=False
        )
        onnx_path = model_path.replace('.pt', '.onnx')
        print(f"✅ ONNX export SUCCESS: {onnx_path}")
        
        if use_gpu:
            print("   → Có thể chạy trên GPU với onnxruntime-gpu")
            print("   → Cài đặt: pip install onnxruntime-gpu")
        else:
            print("   → Có thể chạy trên CPU với onnxruntime")
            print("   → Cài đặt: pip install onnxruntime")
        
        return True
    except Exception as e:
        print(f"❌ ONNX export FAILED: {e}")
        return False

def export_model():
    """Main function để export model"""
    # 1. Kiểm tra GPU
    has_gpu = check_gpu_status()
    
    # 2. Load model
    model_path = 'F:\\BDataFinalProject\\yolov8n.pt'
    print(f"\n📦 Loading model: {model_path}")
    
    try:
        model = YOLO(model_path)
        print("✅ Model loaded successfully")
    except Exception as e:
        print(f"❌ Không thể load model: {e}")
        return
    
    # 3. Export based on GPU availability
    print("\n" + "=" * 60)
    print("🔄 BẮT ĐẦU EXPORT")
    print("=" * 60)
    
    success_count = 0
    
    if has_gpu:
        # Export to TensorRT (GPU only)
        if export_to_tensorrt(model, model_path):
            success_count += 1
        
        # Export to ONNX (GPU-optimized)
        if export_to_onnx(model, model_path, use_gpu=True):
            success_count += 1
    else:
        # Export to ONNX (CPU-compatible)
        print("\n⚠️ Không có GPU - chỉ export ONNX (CPU mode)")
        if export_to_onnx(model, model_path, use_gpu=False):
            success_count += 1
    
    # 4. Summary
    print("\n" + "=" * 60)
    print("📊 KẾT QUẢ")
    print("=" * 60)
    if success_count > 0:
        print(f"✅ Đã export thành công {success_count} format(s)")
        if has_gpu:
            print("\n🎯 Recommended usage:")
            print("   - TensorRT (.engine): Fastest on GPU")
            print("   - ONNX (.onnx): Portable, works with onnxruntime-gpu")
        else:
            print("\n🎯 ONNX model đã sẵn sàng sử dụng trên CPU")
    else:
        print("❌ Không có format nào được export thành công")
    print("=" * 60)

if __name__ == '__main__':
    export_model()