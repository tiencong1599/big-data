# file: spark/converter.py
import tensorrt as trt
import os
import sys

def build_engine(onnx_file_path, engine_file_path):
    print(f"⚙️ STARTING AUTO-CONVERSION: {onnx_file_path} -> {engine_file_path}")
    
    # 1. Setup Logger
    TRT_LOGGER = trt.Logger(trt.Logger.WARNING)
    
    # 2. Setup Builder
    builder = trt.Builder(TRT_LOGGER)
    
    # Tạo network flag (Explicit Batch là bắt buộc cho YOLOv8)
    network_creation_flag = 1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH)
    network = builder.create_network(network_creation_flag)
    
    # 3. Setup Config
    config = builder.create_builder_config()
    
    # Cấp phát bộ nhớ để build (ví dụ 4GB), điều chỉnh nếu RAM GPU thấp
    # Với TRT 8.6+: set_memory_pool_limit
    try:
        config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, 4 * 1024 * 1024 * 1024) 
    except AttributeError:
        # Fallback cho bản cũ
        config.max_workspace_size = 4 * 1024 * 1024 * 1024

    # 4. Parse ONNX
    parser = trt.OnnxParser(network, TRT_LOGGER)
    if not os.path.exists(onnx_file_path):
        print(f"❌ Error: ONNX file not found at {onnx_file_path}")
        sys.exit(1)

    with open(onnx_file_path, 'rb') as model:
        if not parser.parse(model.read()):
            print("❌ Error: Failed to parse ONNX file.")
            for error in range(parser.num_errors):
                print(parser.get_error(error))
            sys.exit(1)

    # 5. Build Engine
    print("⏳ Building TensorRT Engine... (This may take 1-5 minutes)...")
    try:
        serialized_engine = builder.build_serialized_network(network, config)
    except AttributeError:
        # Fallback cho TRT cũ hơn
        engine = builder.build_engine(network, config)
        serialized_engine = engine.serialize()

    if serialized_engine is None:
        print("❌ Error: Build failed.")
        sys.exit(1)

    # 6. Save Engine
    with open(engine_file_path, "wb") as f:
        f.write(serialized_engine)
    
    print(f"✅ SUCCESS: Engine saved to {engine_file_path}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python converter.py <onnx_path> <engine_path>")
        sys.exit(1)
    
    build_engine(sys.argv[1], sys.argv[2])