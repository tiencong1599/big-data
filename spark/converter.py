# file: spark/converter.py
import tensorrt as trt
import os
import sys

def build_engine(onnx_file_path, engine_file_path):
    print(f"⚙️ STARTING AUTO-CONVERSION (Raw Engine): {onnx_file_path} -> {engine_file_path}")
    
    # 1. Setup Logger & Builder
    logger = trt.Logger(trt.Logger.WARNING)
    builder = trt.Builder(logger)
    
    # 2. Tạo network với Explicit Batch (Bắt buộc cho YOLOv8)
    network = builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH))
    parser = trt.OnnxParser(network, logger)
    config = builder.create_builder_config()

    # 3. Parse ONNX
    if not os.path.exists(onnx_file_path):
        print(f"❌ Error: ONNX file not found at {onnx_file_path}")
        sys.exit(1)

    print(f"Reading ONNX file...")
    with open(onnx_file_path, 'rb') as model:
        if not parser.parse(model.read()):
            print("❌ Error: Failed to parse ONNX file.")
            for error in range(parser.num_errors):
                print(parser.get_error(error))
            sys.exit(1)

    # 4. Cấu hình bộ nhớ (Memory Pool) - Quan trọng cho TRT 10.x
    # Cho phép dùng tối đa 2GB RAM cho workspace
    try:
        config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 2 * (1 << 30)) 
    except AttributeError:
        # Fallback nếu dùng bản cũ hơn (đề phòng)
        config.max_workspace_size = 2 * (1 << 30)

    # 5. Bật FP16 nếu GPU hỗ trợ (GTX 1650 Ti có hỗ trợ)
    if builder.platform_has_fast_fp16:
        print("✓ Enabling FP16 precision")
        config.set_flag(trt.BuilderFlag.FP16)

    # 6. Build Engine
    print("⏳ Building Engine (Raw)... This may take a few minutes...")
    try:
        serialized_engine = builder.build_serialized_network(network, config)
    except Exception as e:
        print(f"❌ Build Error: {e}")
        sys.exit(1)

    # 7. Lưu file
    if serialized_engine:
        with open(engine_file_path, "wb") as f:
            f.write(serialized_engine)
        print(f"✅ Success! Clean engine saved to: {engine_file_path}")
    else:
        print("❌ Error: Build failed (serialized_engine is None).")
        sys.exit(1)

build_engine(sys.argv[1], sys.argv[2])