@echo off
echo ============================================================
echo Installing PyTorch with CUDA GPU Support
echo ============================================================
echo.
echo This will install PyTorch with CUDA 11.8 support
echo (Compatible with most NVIDIA GPUs)
echo.
echo If you have a newer GPU and CUDA 12.1, you can use:
echo pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
echo.
pause

echo.
echo Uninstalling old PyTorch (if exists)...
C:\Users\tienc\venv\Scripts\python.exe -m pip uninstall -y torch torchvision torchaudio

echo.
echo Installing PyTorch with CUDA 11.8...
C:\Users\tienc\venv\Scripts\python.exe -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

echo.
echo ============================================================
echo Verifying Installation...
echo ============================================================
C:\Users\tienc\venv\Scripts\python.exe -c "import torch; print(f'PyTorch Version: {torch.__version__}'); print(f'CUDA Available: {torch.cuda.is_available()}'); print(f'CUDA Version: {torch.version.cuda}'); print(f'GPU Name: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"No GPU\"}') "

echo.
echo ============================================================
echo Installation Complete!
echo ============================================================
pause
