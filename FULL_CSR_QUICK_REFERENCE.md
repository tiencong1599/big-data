# 🚀 Full CSR Quick Reference Guide

## Architecture Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  Video File     │────▶│  MJPEG Server    │────▶│  Frontend <img>  │
│  (Storage)      │     │  (Backend)       │     │  (30 FPS Video)  │
└─────────────────┘     └──────────────────┘     └──────────────────┘
                                                           │
                                                           │ Overlay
                                                           ▼
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  Redis Producer │────▶│  Spark Processor │────▶│  WebSocket       │
│  (Metadata)     │     │  (YOLO + Track)  │     │  (Detections)    │
└─────────────────┘     └──────────────────┘     └──────────────────┘
                                                           │
                                                           ▼
                                                  ┌──────────────────┐
                                                  │  Canvas Overlay  │
                                                  │  (Bounding Boxes)│
                                                  └──────────────────┘
```

---

## Data Flow

### **Track 1: Video Stream (MJPEG)**
1. Backend reads video file with OpenCV
2. Encodes frames as JPEG
3. Streams via HTTP (multipart/x-mixed-replace)
4. Frontend displays in `<img>` tag

### **Track 2: Metadata Stream (WebSocket)**
1. Producer sends frame metadata to Redis (500 bytes)
2. Processor reads frame from file, runs YOLO
3. Sends detection metadata to Redis
4. Consumer forwards to Backend WebSocket
5. Frontend draws bounding boxes on canvas

---

## Key Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/video/stream/<video_id>` | GET | MJPEG video stream |
| `/api/producer/stream` | POST | Start metadata producer |
| `/backend_processed_frame` | WebSocket | Detection metadata |

---

## Redis Streams

| Stream Name | Purpose | Payload Size | Data |
|-------------|---------|--------------|------|
| `video-frames` | Producer → Processor | 500 bytes | `{video_id, frame_number, timestamp, config}` |
| `processed-frames` | Processor → Consumer | 500 bytes | `{video_id, frame_number, vehicles[], total_vehicles}` |

---

## Frontend Components

### **video-detail.component.ts**
- **Properties**:
  - `mjpegStreamUrl`: MJPEG stream URL
  - `vehicles`: Array of detected vehicles
  - `canvas`, `ctx`: Canvas overlay for drawing
  
- **Methods**:
  - `startMJPEGStream()`: Load video stream
  - `drawDetections()`: Draw bounding boxes on canvas
  - `stopMJPEGStream()`: Stop stream and clear canvas

### **video-detail.component.html**
```html
<div class="video-container">
  <!-- Video stream (background) -->
  <img [src]="mjpegStreamUrl">
  
  <!-- Detection overlay (foreground) -->
  <canvas #videoCanvas class="detection-overlay"></canvas>
</div>
```

---

## Configuration Changes

### **Producer Config**
```python
# Before
message = {
    'frame_data': base64_encode(frame),  # 2 MB
    ...
}

# After
message = {
    'video_id': str(video_id),
    'frame_number': str(frame_number),
    'timestamp': str(timestamp),
    'config': json.dumps(config)  # Only on first frame
}
```

### **Processor Config**
```python
# Before
frame = decode_base64(frame_data.get(b'frame_data'))

# After
video_path = config_data.get('video_path')
frame = self.read_frame_from_video(video_id, video_path, frame_number)
```

---

## Performance Metrics

| Metric | Value |
|--------|-------|
| **Redis Payload** | 500 bytes/frame |
| **MJPEG Bandwidth** | ~1-2 MB/s @ 30 FPS |
| **Metadata Bandwidth** | ~15 KB/s @ 30 FPS |
| **Total Bandwidth** | ~2 MB/s (vs 60 MB/s before) |
| **Latency** | Real-time (< 100ms) |

---

## Troubleshooting Checklist

- [ ] Backend running on port 8888
- [ ] Redis running on port 6379
- [ ] Spark processor connected to Redis
- [ ] Video file exists in database path
- [ ] Frontend connected to WebSocket
- [ ] MJPEG stream loads in browser
- [ ] Canvas overlay positioned correctly
- [ ] Bounding boxes drawn on canvas

---

## Testing Commands

```bash
# Test MJPEG stream directly
curl http://localhost:8888/api/video/stream/1

# Test WebSocket connection (use browser console)
ws = new WebSocket('ws://localhost:8888/backend_processed_frame');
ws.onmessage = (e) => console.log(JSON.parse(e.data));

# Check Redis streams
redis-cli
> XLEN video-frames
> XLEN processed-frames
> XREAD STREAMS video-frames 0
```

---

## Common Issues

### **MJPEG Stream 404**
- **Cause**: Video file not found
- **Fix**: Check `file_path` in database matches actual file location

### **Canvas Not Visible**
- **Cause**: z-index or position incorrect
- **Fix**: Ensure `.detection-overlay` has `position: absolute` and `z-index: 10`

### **Detections Not Appearing**
- **Cause**: WebSocket not connected
- **Fix**: Check browser console for WebSocket errors

### **Video/Metadata Out of Sync**
- **Cause**: Streams started at different times
- **Fix**: Start both streams simultaneously in `startStream()` method

---

## Code Snippets

### **Draw Bounding Box (Frontend)**
```typescript
drawDetections() {
  this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
  
  this.vehicles.forEach((vehicle) => {
    const { bbox, track_id, speed } = vehicle;
    const color = this.getVehicleColor(track_id);
    
    // Draw box
    this.ctx.strokeStyle = color;
    this.ctx.lineWidth = 3;
    this.ctx.strokeRect(bbox.x1, bbox.y1, 
                         bbox.x2 - bbox.x1, 
                         bbox.y2 - bbox.y1);
    
    // Draw label
    const label = `ID: ${track_id} | ${speed.toFixed(1)} km/h`;
    this.ctx.fillStyle = color;
    this.ctx.fillText(label, bbox.x1 + 5, bbox.y1 - 5);
  });
}
```

### **MJPEG Stream (Backend)**
```python
def get(self, video_id):
    self.set_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
    
    cap = cv2.VideoCapture(video_path)
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        _, jpeg = cv2.imencode('.jpg', frame)
        
        self.write(b'--frame\r\n')
        self.write(b'Content-Type: image/jpeg\r\n\r\n')
        self.write(jpeg.tobytes())
        self.write(b'\r\n')
        yield self.flush()
        
        yield tornado.gen.sleep(1.0 / fps)
```

---

## Migration Checklist

- [x] Create MJPEG streaming handler
- [x] Remove Base64 from producer
- [x] Update processor to read from file
- [x] Add canvas overlay to frontend
- [x] Update TypeScript models
- [x] Add CSS styles
- [x] Test MJPEG stream
- [x] Test WebSocket metadata
- [x] Verify bounding boxes display
- [x] Test end-to-end flow

---

## 📚 Additional Resources

- **MJPEG Format**: [RFC 2046](https://tools.ietf.org/html/rfc2046)
- **Canvas API**: [MDN Canvas Tutorial](https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API/Tutorial)
- **Redis Streams**: [Redis Streams Intro](https://redis.io/topics/streams-intro)
- **Tornado Async**: [Tornado Documentation](https://www.tornadoweb.org/en/stable/)
