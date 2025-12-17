import torch

# Kiểm tra xem có thấy GPU không
has_gpu = torch.cuda.is_available()

if has_gpu:
    print(f"✅ PyTorch đã nhận diện GPU: {torch.cuda.get_device_name(0)}")
    print(f"Số lượng GPU: {torch.cuda.device_count()}")
else:
    print("❌ PyTorch đang chạy bằng CPU. Hãy kiểm tra lại việc cài đặt CUDA.")