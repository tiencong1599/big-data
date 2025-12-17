@echo off
echo Installing required packages...
C:\Users\tienc\venv\Scripts\python.exe -m pip install ultralytics onnx onnxruntime

echo.
echo Running model export...
C:\Users\tienc\venv\Scripts\python.exe transform_model.py

pause
