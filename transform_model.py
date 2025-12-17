"""
YOLOv8 Model Export Tool
========================
Export YOLOv8 models to ONNX and TensorRT formats for deployment.

USAGE EXAMPLES:
--------------
1. Export both ONNX and TensorRT (recommended):
   python transform_model.py --input yolov8n.pt --both

2. Export only ONNX (CPU/GPU compatible):
   python transform_model.py --input yolov8n.pt --onnx

3. Export only TensorRT engine (GPU only, fastest):
   python transform_model.py --input yolov8n.pt --engine

4. Custom image size:
   python transform_model.py --input yolov8n.pt --both --imgsz 640

5. Convert existing ONNX to TensorRT:
   python transform_model.py --onnx-to-engine yolov8n.onnx

SUPPORTED MODEL SIZES:
---------------------
- yolov8n.pt (Nano) - 3.2M params, fastest, recommended
- yolov8s.pt (Small) - 11.2M params
- yolov8m.pt (Medium) - 25.9M params
- yolov8l.pt (Large) - 43.7M params
- yolov8x.pt (Extra Large) - 68.2M params
"""
import argparse
from ultralytics import YOLO
import torch
import sys
import os

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

def export_to_onnx(model_path, output_path='yolov8n.onnx', imgsz=640):
    """Export PyTorch model to ONNX format"""
    print(f"Loading model: {model_path}")
    model = YOLO(model_path)
    
    print(f"Exporting to ONNX: {output_path}")
    model.export(
        format='onnx',
        imgsz=imgsz,
        simplify=True,
        opset=12,
        dynamic=False
    )
    print(f"✓ ONNX model saved: {output_path}")

def export_to_tensorrt(model_path, output_path='yolov8n.engine', imgsz=640, fp16=True, device=0):
    """Export PyTorch model to TensorRT engine format"""
    print(f"Loading model: {model_path}")
    model = YOLO(model_path)
    
    print(f"Exporting to TensorRT: {output_path}")
    print(f"  Image size: {imgsz}x{imgsz}")
    print(f"  FP16: {fp16}")
    print(f"  Device: cuda:{device}")
    
    model.export(
        format='engine',
        imgsz=imgsz,
        half=fp16,  # Use FP16 precision for faster inference
        device=device,
        workspace=4,  # Max workspace size in GB
        verbose=True
    )
    print(f"✓ TensorRT engine saved: {output_path}")
    print("\nNote: TensorRT engines are GPU-specific. This engine is optimized for your current GPU.")

def convert_onnx_to_tensorrt(onnx_path, engine_path='yolov8n.engine', fp16=True, device=0):
    """Convert ONNX model to TensorRT engine using trtexec"""
    import subprocess
    
    print(f"Converting ONNX to TensorRT engine...")
    print(f"  Input: {onnx_path}")
    print(f"  Output: {engine_path}")
    print(f"  FP16: {fp16}")
    
    cmd = [
        'trtexec',
        f'--onnx={onnx_path}',
        f'--saveEngine={engine_path}',
        '--explicitBatch',
    ]
    
    if fp16:
        cmd.append('--fp16')
    
    try:
        subprocess.run(cmd, check=True)
        print(f"✓ TensorRT engine saved: {engine_path}")
    except FileNotFoundError:
        print("Error: trtexec not found. Install TensorRT: pip install tensorrt")
    except subprocess.CalledProcessError as e:
        print(f"Error during conversion: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Convert YOLOv8 models to different formats')
    parser.add_argument('--input', default='yolov8n.pt', help='Input model path (.pt)')
    parser.add_argument('--output', default='yolov8n.engine', help='Output file path')
    parser.add_argument('--format', choices=['onnx', 'engine', 'both'], default='both',
                       help='Export format: onnx, engine, or both')
    parser.add_argument('--imgsz', type=int, default=640, help='Image size (default: 640)')
    parser.add_argument('--fp16', action='store_true', default=True, help='Use FP16 precision')
    parser.add_argument('--device', type=int, default=0, help='CUDA device id')
    parser.add_argument('--onnx-to-engine', help='Convert existing ONNX to TensorRT engine')
    
    args = parser.parse_args()
    
    if args.onnx_to_engine:
        # Convert existing ONNX to TensorRT
        convert_onnx_to_tensorrt(args.onnx_to_engine, args.output, args.fp16, args.device)
    else:
        # Export from PyTorch
        if args.format in ['onnx', 'both']:
            onnx_output = args.output if args.format == 'onnx' else 'yolov8n.onnx'
            export_to_onnx(args.input, onnx_output, args.imgsz)
        
        if args.format in ['engine', 'both']:
            engine_output = args.output if args.format == 'engine' else 'yolov8n.engine'
            export_to_tensorrt(args.input, engine_output, args.imgsz, args.fp16, args.device)
    
    print("\n=== Model Conversion Complete ===")
    print("\nUsage:")
    print("1. Place yolov8n.engine in project root for GPU acceleration")
    print("2. Place yolov8n.onnx as fallback for CPU/non-TensorRT environments")
    print("3. Rebuild Docker: docker-compose build spark")
    print("4. Deploy: docker-compose up -d spark")