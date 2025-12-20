# Performance Debugging Strategy - 2-3 FPS Issue

## Current Architecture Overview

```
Video File → Backend Redis Producer → Redis Stream (video-frames)
                                          ↓
                                    Spark Processor (Detection/Tracking)
                                          ↓
                            Redis Stream (processed-frames)
                                          ↓
                            Redis Consumer → Backend WebSocket → Frontend
```

## Potential Bottlenecks (Ranked by Likelihood)

### 🔴 **CRITICAL SUSPECTS**

#### 1. **Frame Encoding/Decoding Overhead** (Most Likely)
**Location:** `backend/services/redis_producer.py` + `spark/redis_frame_processor.py`

**Problem:**
- Each frame is encoded to base64 (JPEG quality 60) by producer
- Each frame is decoded from base64 by processor
- Base64 adds ~33% size overhead
- JPEG encoding/decoding is CPU-intensive

**Debug Steps:**
```python
# Add timing in redis_producer.py stream_video()
encode_start = time.time()
_, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
frame_base64 = base64.b64encode(buffer).decode('utf-8')
encode_time = (time.time() - encode_start) * 1000
if frame_number % 10 == 0:
    print(f"Encode time: {encode_time:.1f}ms, size: {len(frame_base64)/1024:.1f}KB")
```

**Solutions:**
- ✅ **Best:** Send raw frame bytes (no base64, no JPEG re-encoding)
- ✅ Reduce frame resolution: `frame = cv2.resize(frame, (640, 480))`
- ✅ Lower JPEG quality: `cv2.IMWRITE_JPEG_QUALITY, 40`
- ✅ Skip frames: Process every 2nd or 3rd frame

---

#### 2. **TensorRT Inference Bottleneck**
**Location:** `spark/detector.py` detect()

**Problem:**
- GPU inference might be slower than expected
- Memory copy operations (CPU ↔ GPU) add latency
- Model size (yolov8n vs yolov8s)

**Debug Steps:**
```python
# Add detailed timing in detector.py detect()
def detect(self, image):
    times = {}
    
    t0 = time.time()
    input_tensor, scale, input_size = self.preprocess(image)
    times['preprocess'] = (time.time() - t0) * 1000
    
    t0 = time.time()
    cuda.memcpy_htod(self.inputs[0]['allocation'], np.ascontiguousarray(input_tensor))
    times['h2d_copy'] = (time.time() - t0) * 1000
    
    t0 = time.time()
    self.context.execute_async_v3(stream_handle=0)
    times['inference'] = (time.time() - t0) * 1000
    
    t0 = time.time()
    cuda.memcpy_dtoh(output_data, output_binding['allocation'])
    times['d2h_copy'] = (time.time() - t0) * 1000
    
    t0 = time.time()
    # ... postprocessing ...
    times['postprocess'] = (time.time() - t0) * 1000
    
    total = sum(times.values())
    print(f"[DETECTOR] Total: {total:.1f}ms | " + 
          f"Pre: {times['preprocess']:.1f}ms | " +
          f"H2D: {times['h2d_copy']:.1f}ms | " +
          f"Infer: {times['inference']:.1f}ms | " +
          f"D2H: {times['d2h_copy']:.1f}ms | " +
          f"Post: {times['postprocess']:.1f}ms")
    
    return final_detections
```

**Expected Performance:**
- YOLOv8n on GPU: **5-15ms** per frame
- YOLOv8s on GPU: **10-25ms** per frame
- If > 50ms → Problem!

**Solutions:**
- Use smaller model (yolov8n instead of yolov8s)
- Enable FP16 inference
- Batch processing (process multiple frames at once)

---

#### 3. **Redis Stream Processing Mode**
**Location:** `spark/redis_frame_processor.py` main()

**Problem:**
- Currently processing 1 frame at a time with `count=1`
- 1 second blocking timeout with `block=1000`
- Not utilizing batch processing capabilities

**Current Code:**
```python
messages = redis_client.xreadgroup(
    groupname='spark-processor-group',
    consumername='processor-1',
    streams={REDIS_INPUT_STREAM: last_id},
    count=1,  # ⚠️ Only 1 frame at a time
    block=1000  # ⚠️ 1 second blocking
)
```

**Solutions:**
- ✅ **Reduce block time:** `block=100` (100ms)
- ✅ **Batch processing:** `count=5` (process 5 frames in batch)
- ✅ **Non-blocking mode:** `block=0` with smart polling

---

#### 4. **Tracking Algorithm Overhead**
**Location:** `spark/tracker.py`

**Problem:**
- DeepSORT/SORT tracking can be expensive
- IoU calculation for all track-detection pairs
- Feature extraction (if using Deep features)

**Debug Steps:**
```python
# Add timing in redis_frame_processor.py process_frame()
t0 = time.time()
detections = detector.detect(frame)
detect_time = (time.time() - t0) * 1000

t0 = time.time()
tracks = tracker.update(frame, detections)
track_time = (time.time() - t0) * 1000

t0 = time.time()
speeds = speed_estimator.update(tracks, frame_number)
speed_time = (time.time() - t0) * 1000

print(f"[TIMING] Detect: {detect_time:.1f}ms | Track: {track_time:.1f}ms | Speed: {speed_time:.1f}ms")
```

---

### 🟡 **MEDIUM SUSPECTS**

#### 5. **Redis Connection Latency**
- Multiple Redis operations per frame
- Network latency between services
- Serialization/deserialization overhead

**Debug:**
```python
# Measure Redis operations
t0 = time.time()
redis_client.xadd(REDIS_OUTPUT_STREAM, result, maxlen=1000)
redis_time = (time.time() - t0) * 1000
print(f"Redis XADD: {redis_time:.1f}ms")
```

---

#### 6. **Frame Visualization Overhead**
**Location:** `spark/visualizer.py`

**Problem:**
- Drawing bounding boxes, text, ROI polygons
- Color conversions
- Image copying

**Debug:**
```python
# Time visualization
t0 = time.time()
processed_frame = visualizer.draw_results(frame, vehicles, roi_polygon, speeds)
vis_time = (time.time() - t0) * 1000
print(f"Visualization: {vis_time:.1f}ms")
```

---

### 🟢 **LOW PROBABILITY**

#### 7. **Speed Estimation Calculations**
- Homography transformations
- Kalman filters
- Should be < 1ms per vehicle

#### 8. **WebSocket Transmission**
- Only happens if clients are connected
- Already optimized with subscription cache

#### 9. **Database Operations**
- Analytics tracking writes to Postgres
- Should be async and not blocking frame processing

---

## 🎯 **ACTION PLAN - Step by Step**

### Phase 1: Measure Everything (30 minutes)

1. **Add comprehensive timing to `redis_frame_processor.py`:**

```python
def process_frame(self, frame_data):
    timing = {}
    frame_start = time.time()
    
    # ... existing code ...
    
    video_id = int(frame_data['video_id'])
    frame_number = int(frame_data['frame_number'])
    
    # Decode timing
    t0 = time.time()
    frame = self.decode_from_base64(frame_base64)
    timing['decode'] = (time.time() - t0) * 1000
    
    # Detection timing
    t0 = time.time()
    detections = detector.detect(frame)
    timing['detection'] = (time.time() - t0) * 1000
    
    # Tracking timing
    t0 = time.time()
    tracks = tracker.update(frame, detections)
    timing['tracking'] = (time.time() - t0) * 1000
    
    # Speed estimation timing
    t0 = time.time()
    speeds = speed_estimator.update(tracks, frame_number)
    timing['speed'] = (time.time() - t0) * 1000
    
    # Visualization timing
    t0 = time.time()
    processed_frame = visualizer.draw_results(...)
    timing['visualization'] = (time.time() - t0) * 1000
    
    # Encoding timing
    t0 = time.time()
    frame_encoded = self.encode_to_base64(processed_frame)
    timing['encode'] = (time.time() - t0) * 1000
    
    total_time = (time.time() - frame_start) * 1000
    timing['total'] = total_time
    
    # LOG EVERYTHING
    print(f"\n[FRAME {frame_number}] TIMING BREAKDOWN:")
    print(f"  Decode:        {timing['decode']:6.1f}ms")
    print(f"  Detection:     {timing['detection']:6.1f}ms")
    print(f"  Tracking:      {timing['tracking']:6.1f}ms")
    print(f"  Speed Est:     {timing['speed']:6.1f}ms")
    print(f"  Visualization: {timing['visualization']:6.1f}ms")
    print(f"  Encode:        {timing['encode']:6.1f}ms")
    print(f"  TOTAL:         {timing['total']:6.1f}ms ({1000/total_time:.1f} FPS)")
    
    return result
```

2. **Add timing to producer (`redis_producer.py`):**

```python
def stream_video(self, video_id, video_path):
    cap = cv2.VideoCapture(video_path)
    frame_number = 0
    
    while cap.isOpened():
        t0 = time.time()
        ret, frame = cap.read()
        read_time = (time.time() - t0) * 1000
        
        if not ret:
            break
        
        t0 = time.time()
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
        frame_base64 = base64.b64encode(buffer).decode('utf-8')
        encode_time = (time.time() - t0) * 1000
        
        t0 = time.time()
        message_id = self.redis_client.xadd(REDIS_VIDEO_STREAM, message, maxlen=1000)
        redis_time = (time.time() - t0) * 1000
        
        if frame_number % 30 == 0:
            print(f"[PRODUCER Frame {frame_number}] " +
                  f"Read: {read_time:.1f}ms | " +
                  f"Encode: {encode_time:.1f}ms ({len(frame_base64)/1024:.1f}KB) | " +
                  f"Redis: {redis_time:.1f}ms")
        
        frame_number += 1
```

3. **Run system and collect data**

### Phase 2: Quick Wins (15 minutes)

Based on measurements, apply **quick optimizations:**

1. **Reduce encoding overhead:**
```python
# In redis_producer.py - lower quality
_, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 40])

# OR resize frames
frame = cv2.resize(frame, (640, 480))
```

2. **Reduce Redis blocking:**
```python
# In redis_frame_processor.py
messages = redis_client.xreadgroup(
    groupname='spark-processor-group',
    consumername='processor-1',
    streams={REDIS_INPUT_STREAM: last_id},
    count=1,
    block=100  # Changed from 1000ms to 100ms
)
```

3. **Skip frame processing if no subscribers:**
```python
# Check subscription cache before heavy processing
has_subs = self.redis_client.get(f'websocket:subscription:video:{video_id}')
if not has_subs:
    # Skip detection/tracking, just acknowledge
    continue
```

### Phase 3: Major Optimizations (If needed)

If still < 10 FPS after Phase 2:

1. **Switch to raw bytes instead of base64**
2. **Implement batch processing**
3. **Use smaller YOLO model (nano)**
4. **Enable FP16 inference**
5. **Add frame skipping (process every Nth frame)**

---

## 🔧 **Expected Results**

| Component | Expected Time | If Exceeds | 
|-----------|--------------|------------|
| Frame Decode | < 10ms | Check image size/quality |
| YOLO Detection | 10-30ms | Check GPU utilization |
| Tracking | < 5ms | Too many objects? |
| Speed Estimation | < 2ms | Normal |
| Visualization | 5-15ms | Drawing too much? |
| Frame Encode | < 10ms | Lower quality |
| **TOTAL** | **40-80ms** | **12-25 FPS target** |

If total > 300ms (3 FPS) → **Major bottleneck exists**

---

## 📊 **Monitoring Commands**

```bash
# Check GPU utilization
nvidia-smi -l 1

# Check Redis stream length
redis-cli XLEN video-frames
redis-cli XLEN processed-frames

# Check Docker container resources
docker stats

# Check Python CPU usage
htop / Task Manager
```

---

## ✅ **Next Steps**

1. **Run Phase 1** - Add all timing logs
2. **Identify bottleneck** - Find which operation takes > 100ms
3. **Apply targeted fix** - Optimize the slowest component
4. **Measure again** - Verify improvement
5. **Iterate** - Repeat until reaching target FPS

**Target: 15-20 FPS** (50-65ms per frame total processing time)
