# 🔧 Full CSR Troubleshooting Guide

## Quick Diagnostic Commands

```bash
# Check if backend is running
curl http://localhost:8888/api/videos

# Test MJPEG stream directly
curl http://localhost:8888/api/video/stream/1

# Check Redis streams
redis-cli XLEN video-frames
redis-cli XLEN processed-frames

# Monitor Redis in real-time
redis-cli MONITOR

# Check if Spark processor is connected
redis-cli CLIENT LIST | grep processor

# Check WebSocket connections
netstat -an | grep 8888
```

---

## Common Issues & Solutions

### 🚫 Issue 1: MJPEG Stream Returns 404

**Symptoms**:
- Frontend shows "Waiting for frames..."
- Browser console: `GET http://localhost:8888/api/video/stream/1 404`

**Possible Causes**:
1. Video not found in database
2. Video file path incorrect
3. Backend route not registered

**Solutions**:

```bash
# 1. Check video exists in database
psql -U postgres -d video_processing
SELECT id, name, file_path FROM videos;

# 2. Verify file path exists
# (Replace with actual path from database)
ls -la "F:\videos\traffic.mp4"

# 3. Check backend logs
# Look for: "Initializing application with handlers"
# Should see: "/api/video/stream/(\d+) -> VideoStreamHandler"
```

**Fix**:
```python
# In backend/app.py, verify route is added:
handlers = [
    ...
    (r"/api/video/stream/(\d+)", VideoStreamHandler),
    ...
]
```

---

### 🚫 Issue 2: Video Displays But No Bounding Boxes

**Symptoms**:
- MJPEG stream loads correctly
- Vehicle list shows vehicles
- But no bounding boxes visible on video

**Possible Causes**:
1. Canvas not overlaying video correctly
2. Canvas size mismatch
3. Drawing function not called
4. Z-index issue

**Solutions**:

```typescript
// 1. Check ngAfterViewInit is called
ngAfterViewInit() {
  console.log('[DEBUG] Canvas ref:', this.canvasRef);
  if (this.canvasRef) {
    this.canvas = this.canvasRef.nativeElement;
    this.ctx = this.canvas.getContext('2d');
    console.log('[DEBUG] Canvas context:', this.ctx);
  }
}

// 2. Verify canvas size matches video
startMJPEGStream() {
  this.videoImg = new Image();
  this.videoImg.onload = () => {
    console.log('[DEBUG] Video size:', this.videoImg.width, this.videoImg.height);
    if (this.canvas) {
      this.canvas.width = this.videoImg.width;
      this.canvas.height = this.videoImg.height;
      console.log('[DEBUG] Canvas resized to:', this.canvas.width, this.canvas.height);
    }
  };
  this.videoImg.src = this.mjpegStreamUrl;
}

// 3. Add debug logs to drawDetections
drawDetections() {
  console.log('[DEBUG] Drawing', this.vehicles.length, 'vehicles');
  if (!this.ctx || !this.canvas) {
    console.error('[DEBUG] Canvas not ready');
    return;
  }
  // ... drawing code
}
```

**CSS Fix**:
```css
/* Ensure canvas is overlaying video */
.video-container {
  position: relative;
  width: 100%;
}

.video-stream {
  width: 100%;
  height: auto;
  display: block;
}

.detection-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 10;
}
```

---

### 🚫 Issue 3: Redis Stream Backlog Growing

**Symptoms**:
```bash
$ redis-cli XLEN video-frames
(integer) 5000  # Growing continuously
```

**Possible Causes**:
1. Spark processor not running
2. Processor reading too slow
3. Producer sending too fast

**Solutions**:

```bash
# 1. Check processor is running
ps aux | grep redis_frame_processor

# 2. Check processor logs
tail -f /path/to/spark/logs/processor.log

# 3. Check consumer group
redis-cli XINFO GROUPS video-frames
# Should see: name=processor-group, consumers=1
```

**Fix Backlog**:
```bash
# Option 1: Reset consumer group (DANGEROUS - loses position)
redis-cli XGROUP DESTROY video-frames processor-group
redis-cli XGROUP CREATE video-frames processor-group 0

# Option 2: Skip ahead to latest
redis-cli XGROUP SETID video-frames processor-group $

# Option 3: Increase processor count (if multiple machines)
# Start another instance of redis_frame_processor.py
```

---

### 🚫 Issue 4: Bounding Boxes Incorrect Position

**Symptoms**:
- Bounding boxes drawn in wrong location
- Boxes don't align with vehicles

**Possible Causes**:
1. Canvas size doesn't match video resolution
2. ROI coordinates scaled incorrectly
3. Video resolution changed during processing

**Solutions**:

```typescript
// Force canvas to match video dimensions
startMJPEGStream() {
  this.videoImg = new Image();
  this.videoImg.onload = () => {
    // Get actual displayed size
    const displayWidth = this.videoImg.width;
    const displayHeight = this.videoImg.height;
    
    // Set canvas to match exactly
    this.canvas.width = displayWidth;
    this.canvas.height = displayHeight;
    
    // Store scale factor if needed
    this.scaleX = displayWidth / originalWidth;
    this.scaleY = displayHeight / originalHeight;
  };
}

// Apply scale factor when drawing
drawDetections() {
  this.vehicles.forEach((vehicle) => {
    const bbox = vehicle.bbox;
    
    // Scale coordinates if needed
    const x1 = bbox.x1 * this.scaleX;
    const y1 = bbox.y1 * this.scaleY;
    const x2 = bbox.x2 * this.scaleX;
    const y2 = bbox.y2 * this.scaleY;
    
    this.ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
  });
}
```

**Backend Fix (Ensure Original Resolution)**:
```python
# In spark/redis_frame_processor.py
# Make sure we're NOT resizing frames
frame = self.read_frame_from_video(video_id, video_path, frame_number)
# DO NOT: frame = cv2.resize(frame, (640, 480))

# Keep original resolution
original_height, original_width = frame.shape[:2]
```

---

### 🚫 Issue 5: WebSocket Disconnecting

**Symptoms**:
- Vehicles list updates for a few seconds, then stops
- Browser console: `WebSocket connection closed`

**Possible Causes**:
1. Backend timeout
2. Network interruption
3. Redis consumer crashed

**Solutions**:

```bash
# 1. Check backend logs
tail -f backend.log | grep WebSocket

# 2. Check redis-consumer is running
ps aux | grep redis_consumer

# 3. Test WebSocket manually
node -e "
const ws = new WebSocket('ws://localhost:8888/backend_processed_frame');
ws.onopen = () => console.log('Connected');
ws.onclose = () => console.log('Disconnected');
ws.onmessage = (e) => console.log(e.data);
setTimeout(() => {}, 60000);
"
```

**Backend Fix (Add Ping/Pong)**:
```python
# In backend/handlers/websocket_routing.py
class ClientFrameHandler(tornado.websocket.WebSocketHandler):
    def open(self, video_id):
        # Add periodic ping
        self.ping_callback = tornado.ioloop.PeriodicCallback(
            lambda: self.ping(b"keepalive"),
            30000  # 30 seconds
        )
        self.ping_callback.start()
    
    def on_close(self):
        if hasattr(self, 'ping_callback'):
            self.ping_callback.stop()
```

---

### 🚫 Issue 6: High CPU Usage

**Symptoms**:
- Backend CPU usage > 80%
- System becomes sluggish

**Possible Causes**:
1. MJPEG encoding too frequent
2. Multiple concurrent streams
3. Large video resolution

**Solutions**:

```python
# 1. Add frame skip in MJPEG handler
class VideoStreamHandler(tornado.web.RequestHandler):
    @tornado.gen.coroutine
    def get(self, video_id):
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_delay = 1.0 / fps
        
        # Add frame skip for high FPS videos
        if fps > 30:
            frame_skip = int(fps / 30)
            frame_delay = frame_skip / fps
        else:
            frame_skip = 1
        
        frame_count = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # Skip frames if needed
            if frame_count % frame_skip != 0:
                frame_count += 1
                continue
            
            # ... encode and send
            yield tornado.gen.sleep(frame_delay)

# 2. Reduce JPEG quality
_, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])  # Lower from 85

# 3. Limit concurrent streams
MAX_CONCURRENT_STREAMS = 5
active_streams = {}

def get(self, video_id):
    if len(active_streams) >= MAX_CONCURRENT_STREAMS:
        self.set_status(503)  # Service Unavailable
        self.write({'error': 'Too many active streams'})
        return
```

---

### 🚫 Issue 7: Spark Processor Can't Read Video File

**Symptoms**:
- Processor logs: `Could not open video file: /path/to/video.mp4`
- Processing stops

**Possible Causes**:
1. File path incorrect (Windows vs Linux)
2. File permissions
3. File doesn't exist
4. File format not supported

**Solutions**:

```bash
# 1. Check file exists and is readable
ls -la "/path/to/video.mp4"

# 2. Test OpenCV can read file
python3 << EOF
import cv2
cap = cv2.VideoCapture('/path/to/video.mp4')
print('Opened:', cap.isOpened())
print('Frame count:', cap.get(cv2.CAP_PROP_FRAME_COUNT))
cap.release()
EOF

# 3. Check file permissions
chmod 644 /path/to/video.mp4

# 4. Verify video codec
ffprobe /path/to/video.mp4
```

**Code Fix (Normalize Path)**:
```python
# In backend/models/video.py
import os

def get_video_config(video_id):
    # ...
    video_path = os.path.abspath(video.file_path)
    video_path = video_path.replace('\\', '/')  # Normalize for cross-platform
    
    return {
        'video_path': video_path,
        # ...
    }
```

---

### 🚫 Issue 8: Frontend CORS Error

**Symptoms**:
- Browser console: `Access to fetch at 'http://localhost:8888/api/video/stream/1' from origin 'http://localhost:4200' has been blocked by CORS policy`

**Solution**:

```python
# In backend/handlers/video_stream_handler.py
class VideoStreamHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        # Allow frontend origin
        self.set_header("Access-Control-Allow-Origin", "http://localhost:4200")
        self.set_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.set_header("Access-Control-Allow-Headers", "*")
        self.set_header("Access-Control-Allow-Credentials", "true")
    
    def options(self, video_id):
        # Handle preflight
        self.set_status(204)
        self.finish()
```

---

## Debugging Workflow

### Step 1: Verify Backend
```bash
# Start backend
cd backend
python app.py

# Check logs for route registration
# Should see: "/api/video/stream/(\d+) -> VideoStreamHandler"

# Test MJPEG endpoint
curl -I http://localhost:8888/api/video/stream/1
# Should return: Content-Type: multipart/x-mixed-replace; boundary=frame
```

### Step 2: Verify Redis
```bash
# Check Redis is running
redis-cli ping
# Should return: PONG

# Check streams exist
redis-cli XLEN video-frames
redis-cli XLEN processed-frames

# Monitor activity
redis-cli MONITOR
# Start producer, should see XADD commands
```

### Step 3: Verify Spark Processor
```bash
# Start processor
cd spark
python redis_frame_processor.py

# Check logs
# Should see:
# - "✓ FrameProcessor initialized"
# - "✓ Opened video capture for video 1"
# - "✓ Created SpeedEstimator for video 1"

# Check Redis output stream
redis-cli XREAD COUNT 1 STREAMS processed-frames 0
# Should see metadata with vehicles array
```

### Step 4: Verify Frontend
```bash
# Start frontend
cd frontend
ng serve

# Open browser console
# Check for:
# - MJPEG stream loaded: Network tab shows continuous data
# - WebSocket connected: Console shows no errors
# - Canvas initialized: Check elements panel for <canvas>

# Debug in console:
# ws = new WebSocket('ws://localhost:8888/backend_processed_frame');
# ws.onmessage = (e) => console.log(JSON.parse(e.data));
```

---

## Performance Monitoring

### Monitor Redis Bandwidth
```bash
# Install redis-cli monitoring tool
redis-cli --stat

# Watch specific metrics
redis-cli INFO stats | grep instantaneous
# instantaneous_input_kbps: Should be < 20 KB/s
# instantaneous_output_kbps: Should be < 20 KB/s
```

### Monitor Backend Performance
```bash
# CPU usage
top -p $(pgrep -f "python.*app.py")

# Memory usage
ps aux | grep "python.*app.py"

# Network connections
netstat -an | grep 8888 | wc -l
```

### Monitor Spark Processor
```bash
# Processing time per frame
# Add to redis_frame_processor.py:
import time
start = time.time()
result = self.process_frame(frame_data)
elapsed = (time.time() - start) * 1000
print(f"[PERF] Frame {frame_number}: {elapsed:.2f}ms")
```

---

## Health Check Script

```python
#!/usr/bin/env python3
"""
Health check script for Full CSR system
"""
import requests
import redis
import websocket
import json

def check_backend():
    try:
        r = requests.get('http://localhost:8888/api/videos', timeout=5)
        return r.status_code == 200
    except:
        return False

def check_mjpeg_stream(video_id=1):
    try:
        r = requests.get(f'http://localhost:8888/api/video/stream/{video_id}', 
                        stream=True, timeout=5)
        return r.status_code == 200
    except:
        return False

def check_redis():
    try:
        r = redis.Redis(host='localhost', port=6379)
        return r.ping()
    except:
        return False

def check_redis_streams():
    try:
        r = redis.Redis(host='localhost', port=6379)
        input_len = r.xlen('video-frames')
        output_len = r.xlen('processed-frames')
        return input_len >= 0 and output_len >= 0
    except:
        return False

def check_websocket():
    try:
        ws = websocket.WebSocket()
        ws.connect('ws://localhost:8888/backend_processed_frame', timeout=5)
        ws.close()
        return True
    except:
        return False

if __name__ == '__main__':
    print("🔍 Full CSR System Health Check")
    print("=" * 50)
    
    checks = [
        ("Backend API", check_backend),
        ("MJPEG Stream", lambda: check_mjpeg_stream()),
        ("Redis Server", check_redis),
        ("Redis Streams", check_redis_streams),
        ("WebSocket", check_websocket),
    ]
    
    for name, check_fn in checks:
        status = "✅" if check_fn() else "❌"
        print(f"{status} {name}")
    
    print("=" * 50)
```

---

## Rollback Plan

If Full CSR has critical issues, rollback to Base64 SSR:

```bash
# 1. Revert backend producer
git checkout HEAD~1 backend/services/redis_producer.py

# 2. Revert spark processor
git checkout HEAD~1 spark/redis_frame_processor.py

# 3. Revert frontend
git checkout HEAD~1 frontend/src/app/

# 4. Restart services
# Backend
cd backend && python app.py

# Spark
cd spark && python redis_frame_processor.py

# Frontend
cd frontend && ng serve
```

---

## Support & Contact

For issues not covered in this guide:
1. Check GitHub Issues: [link]
2. Contact development team: [email]
3. Review system logs: `backend.log`, `spark.log`, browser console
4. Enable debug mode: Set `DEBUG=true` in environment variables
