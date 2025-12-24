# 🚗 Real-Time Traffic Monitoring System - System Architecture

## 📋 Table of Contents
- [System Overview](#system-overview)
- [Architecture Diagram](#architecture-diagram)
- [Technology Stack](#technology-stack)
- [Components](#components)
- [Data Flow](#data-flow)
- [WebSocket Channels](#websocket-channels)
- [Database Schema](#database-schema)
- [Redis Streams](#redis-streams)
- [Performance Optimization](#performance-optimization)
- [Deployment](#deployment)

---

## 🎯 System Overview

Real-time traffic monitoring system that:
- Processes video streams frame-by-frame
- Detects and tracks vehicles using YOLOv8 + DeepSORT
- Estimates vehicle speeds with homography transformation
- Monitors speeding violations (>60 km/h)
- Provides real-time analytics via WebSocket
- Stores historical data in PostgreSQL

### Key Features
✅ Real-time video streaming with MJPEG encoding  
✅ Vehicle detection and tracking (car, truck, motorcycle, bus)  
✅ Speed estimation using camera calibration  
✅ ROI (Region of Interest) filtering  
✅ Dual-channel WebSocket architecture (frames + analytics)  
✅ Append-only speeding violations log  
✅ Redis-based inter-service communication  
✅ Airflow-based workflow orchestration  
✅ Docker containerized deployment  

---

## 🏗️ Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           FRONTEND (Angular 18)                          │
│  ┌────────────────────┐        ┌────────────────────┐                   │
│  │  Frame Channel     │        │  Analytics Channel  │                   │
│  │  ws://...stream    │        │  ws://...stream     │                   │
│  │  processed_frame_1 │        │  analytics_metrics_1│                   │
│  └─────────┬──────────┘        └─────────┬───────────┘                   │
│            │                              │                               │
│            │ MJPEG Frames                 │ Stats + Speeding Vehicles     │
│            │                              │                               │
└────────────┼──────────────────────────────┼───────────────────────────────┘
             │                              │
             ▼                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      BACKEND (Tornado WebSocket)                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  WebSocket Handlers                                             │    │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────┐ │    │
│  │  │ ClientFrame      │  │ BackendProcessed │  │ BackendAnalytics│ │   │
│  │  │ Handler          │  │ FrameHandler     │  │ Handler         │ │   │
│  │  │ (Client Connect) │  │ (Frame Route)    │  │ (Analytics Route)│ │  │
│  │  └──────────────────┘  └──────────────────┘  └───────────────┘ │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  REST API (Video Management)                                    │    │
│  │  - POST /api/videos/upload                                      │    │
│  │  - GET  /api/videos                                             │    │
│  │  - POST /api/videos/:id/stream/start                            │    │
│  │  - POST /api/videos/:id/stream/stop                             │    │
│  │  - GET  /api/websocket/status                                   │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────┬───────────────────────────────────────────────────┬────────┘
              │                                                   │
              │ Airflow DAG Trigger                              │ Redis Subscription Check
              ▼                                                   ▼
┌──────────────────────────┐                        ┌──────────────────────┐
│   AIRFLOW SCHEDULER      │                        │   REDIS CONSUMER     │
│  ┌────────────────────┐  │                        │  ┌────────────────┐  │
│  │ video_streaming_   │  │                        │  │ Read from      │  │
│  │ pipeline DAG       │  │                        │  │ processed-     │  │
│  │                    │  │                        │  │ frames stream  │  │
│  │ 1. Produce frames  │  │                        │  │                │  │
│  │ 2. Process frames  │  │                        │  │ Route to:      │  │
│  │ 3. Cleanup         │  │                        │  │ - Frame WS     │  │
│  └────────┬───────────┘  │                        │  │ - Analytics WS │  │
└───────────┼──────────────┘                        └──┴────────────────┘
            │                                          ▲
            │ Produce Frames                          │ Consume Results
            ▼                                          │
┌──────────────────────────────────────────────────────────────────────────┐
│                         REDIS STREAMS                                     │
│  ┌────────────────────┐              ┌────────────────────┐              │
│  │  video-frames      │              │  processed-frames  │              │
│  │  (Raw Frame Data)  │              │  (Processed Data)  │              │
│  │                    │              │                    │              │
│  │  - video_id        │              │  - video_id        │              │
│  │  - frame_number    │              │  - frame_number    │              │
│  │  - frame_data      │              │  - processed_frame │              │
│  │  - timestamp       │              │  - vehicles[]      │              │
│  │  - config          │              │  - stats{}         │              │
│  └────────┬───────────┘              │  - roi_polygon     │              │
│           │                          └────────────────────┘              │
└───────────┼──────────────────────────────────────────────────────────────┘
            │ Produce                         ▲ Produce
            ▼                                 │
┌──────────────────────────────────────────────────────────────────────────┐
│                      SPARK PROCESSOR (Python)                             │
│  ┌─────────────────────────────────────────────────────────────────┐     │
│  │  FrameProcessor                                                  │     │
│  │  ┌──────────────┐  ┌───────────┐  ┌──────────────┐  ┌────────┐ │     │
│  │  │ YOLOv8       │→ │ DeepSORT  │→ │ Speed        │→ │ Redis  │ │     │
│  │  │ Detection    │  │ Tracking  │  │ Estimation   │  │ Publish│ │     │
│  │  │ (TensorRT)   │  │           │  │ (Homography) │  │        │ │     │
│  │  └──────────────┘  └───────────┘  └──────────────┘  └────────┘ │     │
│  │                                                                  │     │
│  │  ┌──────────────────────────────────────────────────────────┐   │     │
│  │  │ VehicleAnalyticsTracker                                  │   │     │
│  │  │ - Track vehicles entering/exiting ROI                    │   │     │
│  │  │ - Calculate cumulative total                             │   │     │
│  │  │ - Count current speeding vehicles                        │   │     │
│  │  │ - Generate real-time stats                               │   │     │
│  │  └──────────────────────────────────────────────────────────┘   │     │
│  └─────────────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────────────┘
                                  │
                                  │ Dump Analytics on Stream End
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                       POSTGRESQL DATABASE                                 │
│  ┌─────────────────────┐         ┌─────────────────────┐                 │
│  │  videos             │         │  video_analytics    │                 │
│  │  ─────────────────  │         │  ──────────────────  │                 │
│  │  - id (PK)          │         │  - id (PK)          │                 │
│  │  - name             │         │  - video_id (FK)    │                 │
│  │  - file_path        │         │  - total_vehicles   │                 │
│  │  - roi              │◄────────│  - avg_dwell_time   │                 │
│  │  - homography_matrix│         │  - vehicle_types    │                 │
│  │  - camera_matrix    │         │  - processed_at     │                 │
│  │  - fps              │         │                     │                 │
│  │  - created_at       │         └─────────────────────┘                 │
│  └─────────────────────┘                                                  │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Technology Stack

### Frontend
- **Framework**: Angular 18
- **Language**: TypeScript 5.5
- **WebSocket**: Native WebSocket API
- **State Management**: RxJS Observables
- **Canvas**: HTML5 Canvas for ROI overlay
- **HTTP Client**: Angular HttpClient

### Backend
- **Framework**: Tornado (Python async web server)
- **Language**: Python 3.9+
- **WebSocket**: Tornado WebSocket handlers
- **REST API**: Tornado RequestHandlers
- **Database**: PostgreSQL 15
- **ORM**: SQLAlchemy

### Processing Engine
- **Framework**: PySpark (standalone mode)
- **Computer Vision**: OpenCV 4.8+
- **Detection**: YOLOv8 (TensorRT optimized)
- **Tracking**: DeepSORT
- **Speed Estimation**: Homography transformation
- **Image Encoding**: JPEG compression

### Orchestration
- **Workflow**: Apache Airflow 2.8
- **Scheduler**: Airflow Scheduler
- **Executor**: LocalExecutor

### Data Layer
- **Message Queue**: Redis Streams
- **Cache**: Redis
- **File Storage**: Local filesystem (mounted volumes)

### Deployment
- **Containerization**: Docker
- **Orchestration**: Docker Compose
- **Networking**: Bridge network

---

## 📦 Components

### 1. Frontend (Angular Application)

**Location**: `frontend/`

#### Key Components:
- **DashboardComponent** (`dashboard.component.ts`)
  - Lists all uploaded videos
  - Provides video selection interface
  - Shows video metadata

- **VideoDetailComponent** (`video-detail.component.ts`)
  - Manages dual WebSocket subscriptions:
    - **Frame channel**: `processed_frame_{video_id}`
    - **Analytics channel**: `analytics_metrics_{video_id}`
  - Displays video stream with ROI overlay
  - Shows real-time analytics (total vehicles, speeding count)
  - Maintains append-only speeding violations log
  - Implements watchdog timer for connection monitoring

#### Services:
- **WebsocketService** (`websocket.service.ts`)
  - Manages two separate WebSocket connections
  - Frame channel: Receives MJPEG frames only
  - Analytics channel: Receives stats + speeding vehicles
  - Handles reconnection logic

- **VideoService** (`video.service.ts`)
  - REST API client for video operations
  - Upload, list, start/stop streaming

#### Models:
```typescript
interface VehicleData {
  track_id: number;
  bbox: { x1, y1, x2, y2 };
  speed: number;
  speed_unit: string;
  class_id: number;
  confidence: number;
  detectedAt?: Date;
}

interface FrameStats {
  total_vehicles: number;      // Cumulative total
  speeding_count: number;       // Current >60km/h
  current_in_roi: number;       // Active in ROI
}

interface ProcessedFrameData {
  video_id: number;
  frame_number: number;
  timestamp: number;
  processed_frame: string;      // Base64 JPEG
  roi_polygon: number[][];
  end_of_stream: boolean;
}

interface AnalyticsData {
  video_id: number;
  frame_number: number;
  timestamp: number;
  stats: FrameStats;
  speeding_vehicles: VehicleData[];
}
```

---

### 2. Backend (Tornado Server)

**Location**: `backend/`

#### Main Application (`app.py`)
- Tornado IOLoop-based async server
- Runs on port 8686
- Registers WebSocket and HTTP handlers
- Initializes database connection pool

#### WebSocket Handlers (`handlers/websocket_routing.py`)

##### ClientFrameHandler
- **Route**: `/ws/client/stream`
- **Purpose**: Client WebSocket connections
- **Functionality**:
  - Accepts subscription messages: `{action: 'subscribe', channel: 'processed_frame_1'}`
  - Supports both frame and analytics channels
  - Maintains global `client_subscriptions` registry
  - Caches subscriptions in Redis for redis_consumer optimization
  - Sends subscription acknowledgments

##### BackendProcessedFrameHandler
- **Route**: `/ws/backend/processed`
- **Purpose**: Receives frames from Redis consumer
- **Functionality**:
  - Routes frames to `processed_frame_{video_id}` channels
  - Broadcasts to subscribed clients
  - Handles dead client cleanup

##### BackendAnalyticsHandler
- **Route**: `/ws/backend/analytics`
- **Purpose**: Receives analytics from Redis consumer
- **Functionality**:
  - Routes analytics to `analytics_metrics_{video_id}` channels
  - Broadcasts stats and speeding vehicles
  - Independent from frame channel

#### REST API Handlers

##### VideoHandler (`handlers/video_handler.py`)
- `GET /api/videos` - List all videos
- `POST /api/videos/upload` - Upload new video
- `GET /api/videos/:id` - Get video details
- `POST /api/videos/:id/stream/start` - Trigger Airflow DAG
- `POST /api/videos/:id/stream/stop` - Stop processing

##### WebSocketStatusHandler
- `GET /api/websocket/status` - Returns subscription status
```json
{
  "channels": {
    "processed_frame_1": { "subscriber_count": 2, "video_id": 1 },
    "analytics_metrics_1": { "subscriber_count": 2, "video_id": 1 }
  },
  "total_clients": 4,
  "active_streams": [1]
}
```

#### Redis Consumer (`services/redis_consumer.py`)
- **Purpose**: Bridge between Redis Streams and Backend WebSocket
- **Connections**:
  - WebSocket to `ws://backend:8686/ws/backend/processed` (frames)
  - WebSocket to `ws://backend:8686/ws/backend/analytics` (analytics)
  - Redis consumer group on `processed-frames` stream
- **Logic**:
  - Reads processed frames from Redis
  - Checks Redis cache for active subscriptions
  - Routes frames to frame channel (if subscribers exist)
  - Filters speeding vehicles (>60 km/h)
  - Routes analytics to analytics channel (if subscribers exist)
  - ACKs messages in Redis

---

### 3. Spark Processor (Frame Processing Engine)

**Location**: `spark/`

#### Main Components:

##### FrameProcessor (`redis_frame_processor.py`)
Main processing pipeline:

```python
class FrameProcessor:
    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.analytics_trackers = {}  # {video_id: VehicleAnalyticsTracker}
        
    def process_frame(self, frame_data):
        # 1. Decode frame from base64
        frame = self.decode_from_base64(frame_base64)
        
        # 2. Detect vehicles (YOLOv8)
        detections = detector.detect(frame)
        
        # 3. Apply ROI filter
        if use_roi:
            detections = filter_by_roi(detections, roi_polygon)
        
        # 4. Track vehicles (DeepSORT)
        tracks = tracker.update(frame, detections)
        
        # 5. Estimate speeds
        speeds = speed_estimator.update(tracks, frame_number)
        
        # 6. Update analytics
        tracker = self.get_analytics_tracker(video_id)
        tracker.update(tracks, timestamp)
        stats = tracker.get_frame_stats(speeds)
        
        # 7. Visualize (draw bounding boxes)
        annotated_frame = visualizer.draw_results(frame, tracks, speeds)
        
        # 8. Encode to base64
        processed_frame_base64 = self.encode_to_base64(annotated_frame)
        
        # 9. Build result payload
        return {
            'video_id': video_id,
            'frame_number': frame_number,
            'processed_frame': processed_frame_base64,
            'vehicles': vehicles,  # ALL vehicles
            'stats': stats,        # Backend-calculated stats
            'roi_polygon': roi_polygon
        }
```

##### VehicleAnalyticsTracker (`analytics_tracker.py`)
Real-time analytics engine:

```python
class VehicleAnalyticsTracker:
    def __init__(self, redis_client, video_id):
        self.redis = redis_client
        self.video_id = video_id
        self.total_vehicles_entered = 0
        self.current_vehicles_in_roi = set()
        self.vehicle_enter_times = {}
        
    def update(self, tracks, frame_timestamp):
        # Detect new vehicles entering ROI
        current_track_ids = {track_id for track_id, _ in tracks}
        new_vehicles = current_track_ids - self.current_vehicles_in_roi
        
        for track_id in new_vehicles:
            self.total_vehicles_entered += 1
            self.vehicle_enter_times[track_id] = frame_timestamp
            self.current_vehicles_in_roi.add(track_id)
        
        # Detect vehicles exiting ROI
        exited_vehicles = self.current_vehicles_in_roi - current_track_ids
        for track_id in exited_vehicles:
            dwell_time = frame_timestamp - self.vehicle_enter_times[track_id]
            # Record exit metrics
            self.current_vehicles_in_roi.remove(track_id)
    
    def get_frame_stats(self, current_speeds):
        """Calculate real-time stats for current frame"""
        speeding_count = 0
        for track_id in self.current_vehicles_in_roi:
            if current_speeds.get(track_id, 0) > 60:
                speeding_count += 1
        
        return {
            "total_vehicles": self.total_vehicles_entered,
            "speeding_count": speeding_count,
            "current_in_roi": len(self.current_vehicles_in_roi)
        }
    
    def finalize_and_dump_to_db(self, db_session):
        """Dump analytics to PostgreSQL when stream ends"""
        # Insert into video_analytics table
```

##### Supporting Modules:
- **Detector** (`detector.py`) - YOLOv8 with TensorRT optimization
- **Tracker** (`tracker.py`) - DeepSORT multi-object tracking
- **SpeedEstimator** (`speed_estimator.py`) - Homography-based speed calculation
- **Visualizer** (`visualizer.py`) - Draw bounding boxes and labels

---

### 4. Airflow Workflow Orchestration

**Location**: `airflow/dags/`

#### Video Streaming Pipeline DAG

```python
@dag(
    dag_id='video_streaming_pipeline',
    schedule_interval=None,
    catchup=False
)
def video_streaming_dag():
    
    @task
    def produce_frames(video_id: int):
        """Read video file, extract frames, publish to Redis"""
        # Read from video_storage/{video_id}.mp4
        # Extract frames at specified FPS
        # Publish to 'video-frames' stream
        pass
    
    @task
    def process_frames(video_id: int):
        """Consume frames, process with YOLO+Tracking, publish results"""
        # Consume from 'video-frames' stream
        # Process with FrameProcessor
        # Publish to 'processed-frames' stream
        pass
    
    @task
    def cleanup(video_id: int):
        """Cleanup Redis streams, dump analytics to DB"""
        # Delete consumed messages from streams
        # Call analytics_tracker.finalize_and_dump_to_db()
        pass
    
    # Task dependencies
    produce_task = produce_frames({{ dag_run.conf['video_id'] }})
    process_task = process_frames({{ dag_run.conf['video_id'] }})
    cleanup_task = cleanup({{ dag_run.conf['video_id'] }})
    
    produce_task >> process_task >> cleanup_task
```

---

## 🔄 Data Flow

### Complete End-to-End Flow

#### 1. Video Upload
```
User → Frontend → POST /api/videos/upload → Backend
                                           → Save to video_storage/
                                           → Insert into videos table
                                           → Return video metadata
```

#### 2. Stream Start
```
User → Frontend → POST /api/videos/:id/stream/start
                → Backend → Airflow API: Trigger DAG with video_id
                         → Return dag_run_id
```

#### 3. Frame Production (Airflow Task 1)
```
Airflow produce_frames_task:
  Read video_storage/{video_id}.mp4
  → Extract frame
  → Encode to base64
  → Publish to Redis 'video-frames' stream:
      {
        video_id: 1,
        frame_number: 42,
        frame_data: "base64...",
        timestamp: 1234567890,
        config: { roi_polygon: [...], homography_matrix: [...] }
      }
```

#### 4. Frame Processing (Airflow Task 2)
```
Airflow process_frames_task:
  Consume from 'video-frames' stream
  → FrameProcessor.process_frame():
      1. Decode base64
      2. YOLOv8 detection
      3. ROI filtering
      4. DeepSORT tracking
      5. Speed estimation
      6. Analytics update
      7. Visualization
      8. JPEG encoding
  → Publish to Redis 'processed-frames' stream:
      {
        video_id: 1,
        frame_number: 42,
        processed_frame: "base64_jpeg...",
        vehicles: [
          { track_id: 5, bbox: {...}, speed: 75, class_id: 2 },
          { track_id: 8, bbox: {...}, speed: 45, class_id: 2 }
        ],
        stats: {
          total_vehicles: 123,
          speeding_count: 1,
          current_in_roi: 8
        },
        roi_polygon: [[x1,y1], [x2,y2], ...]
      }
```

#### 5. Redis Consumer Routing
```
Redis Consumer:
  Consume from 'processed-frames' stream
  
  → Check Redis cache for subscriptions:
      has_frame_subscribers(video_id) ?
      has_analytics_subscribers(video_id) ?
  
  → If frame subscribers exist:
      Send to ws://backend:8686/ws/backend/processed
      {
        type: 'processed_frame',
        data: {
          video_id: 1,
          frame_number: 42,
          processed_frame: "base64_jpeg...",
          roi_polygon: [...]
        }
      }
  
  → If analytics subscribers exist:
      Filter speeding vehicles (speed > 60)
      Send to ws://backend:8686/ws/backend/analytics
      {
        type: 'analytics_update',
        data: {
          video_id: 1,
          frame_number: 42,
          stats: { total_vehicles: 123, speeding_count: 1, ... },
          speeding_vehicles: [
            { track_id: 5, speed: 75, ... }
          ]
        }
      }
```

#### 6. Backend WebSocket Routing
```
Backend BackendProcessedFrameHandler:
  Receive frame data
  → Route to channel 'processed_frame_1'
  → Broadcast to all subscribed clients

Backend BackendAnalyticsHandler:
  Receive analytics data
  → Route to channel 'analytics_metrics_1'
  → Broadcast to all subscribed clients
```

#### 7. Frontend Reception
```
Frontend VideoDetailComponent:

Frame Subscription:
  ws.onmessage (frame channel)
  → Update currentFrame
  → Trigger canvas ROI drawing
  → NO re-render

Analytics Subscription:
  ws.onmessage (analytics channel)
  → Update stats display
  → Append NEW speeding vehicles to list
  → NO re-render
```

#### 8. Stream End & Cleanup
```
Airflow cleanup_task:
  → Delete messages from Redis streams
  → Call analytics_tracker.finalize_and_dump_to_db()
  → Insert into video_analytics table:
      {
        video_id: 1,
        total_vehicles_count: 523,
        avg_dwell_time: 12.5,
        vehicle_type_distribution: { car: 450, truck: 50, ... }
      }
```

---

## 🌐 WebSocket Channels

### Channel Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    CLIENT CONNECTIONS                        │
│                                                               │
│  Frontend 1:                                                  │
│    - ws://backend:8686/ws/client/stream                      │
│      Subscribe to: processed_frame_1                         │
│      Subscribe to: analytics_metrics_1                       │
│                                                               │
│  Frontend 2:                                                  │
│    - ws://backend:8686/ws/client/stream                      │
│      Subscribe to: processed_frame_2                         │
│      Subscribe to: analytics_metrics_2                       │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            │ Subscription Messages
                            ▼
┌─────────────────────────────────────────────────────────────┐
│               BACKEND CHANNEL REGISTRY                       │
│                                                               │
│  client_subscriptions = {                                    │
│    'processed_frame_1': {ws_conn1, ws_conn2},               │
│    'analytics_metrics_1': {ws_conn1, ws_conn2},             │
│    'processed_frame_2': {ws_conn3},                         │
│    'analytics_metrics_2': {ws_conn3}                        │
│  }                                                            │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            │ Broadcasts
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                 BACKEND WEBSOCKET SERVERS                    │
│                                                               │
│  ws://backend:8686/ws/backend/processed                      │
│    ← Redis Consumer (frame data)                             │
│    → Routes to processed_frame_{video_id}                    │
│                                                               │
│  ws://backend:8686/ws/backend/analytics                      │
│    ← Redis Consumer (analytics data)                         │
│    → Routes to analytics_metrics_{video_id}                  │
└─────────────────────────────────────────────────────────────┘
```

### Message Formats

#### Subscription Request (Client → Backend)
```json
{
  "action": "subscribe",
  "channel": "processed_frame_1"
}
```

#### Subscription Acknowledgment (Backend → Client)
```json
{
  "type": "subscription_ack",
  "channel": "processed_frame_1",
  "status": "subscribed"
}
```

#### Frame Data (Backend → Client)
```json
{
  "type": "frame",
  "data": {
    "video_id": 1,
    "frame_number": 42,
    "timestamp": 1234567890,
    "processed_frame": "data:image/jpeg;base64,/9j/4AAQ...",
    "roi_polygon": [[100, 200], [300, 200], [300, 400], [100, 400]],
    "end_of_stream": false
  }
}
```

#### Analytics Data (Backend → Client)
```json
{
  "type": "analytics",
  "data": {
    "video_id": 1,
    "frame_number": 42,
    "timestamp": 1234567890,
    "stats": {
      "total_vehicles": 123,
      "speeding_count": 1,
      "current_in_roi": 8
    },
    "speeding_vehicles": [
      {
        "track_id": 5,
        "bbox": { "x1": 100, "y1": 200, "x2": 150, "y2": 250 },
        "speed": 75.5,
        "speed_unit": "km/h",
        "class_id": 2,
        "confidence": 0.95
      }
    ]
  }
}
```

---

## 🗄️ Database Schema

### PostgreSQL Tables

#### videos
```sql
CREATE TABLE videos (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    roi JSONB,                      -- ROI polygon coordinates
    calibrate_coordinates JSONB,    -- Calibration points
    homography_matrix JSONB,        -- 3x3 transformation matrix
    camera_matrix JSONB,            -- Camera intrinsic matrix
    fps REAL DEFAULT 30.0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

#### video_analytics
```sql
CREATE TABLE video_analytics (
    id SERIAL PRIMARY KEY,
    video_id INTEGER REFERENCES videos(id) ON DELETE CASCADE,
    total_vehicles_count INTEGER NOT NULL,
    avg_dwell_time REAL,            -- Average time in ROI (seconds)
    vehicle_type_distribution JSONB, -- { "car": 450, "truck": 50, ... }
    processed_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(video_id)
);
```

### Example Data

#### videos table
```sql
INSERT INTO videos (name, file_path, roi, fps) VALUES (
    'Highway Traffic',
    '/app/video_storage/1.mp4',
    '{"roi_polygon": [[100, 200], [300, 200], [300, 400], [100, 400]]}',
    30.0
);
```

#### video_analytics table
```sql
INSERT INTO video_analytics (
    video_id, 
    total_vehicles_count, 
    avg_dwell_time,
    vehicle_type_distribution
) VALUES (
    1,
    523,
    12.5,
    '{"car": 450, "truck": 50, "motorcycle": 20, "bus": 3}'
);
```

---

## 📊 Redis Streams

### Stream: `video-frames`

**Purpose**: Raw video frames from file reader

**Consumer Group**: `frame-processor-group`

**Message Format**:
```json
{
  "video_id": "1",
  "frame_number": "42",
  "frame_data": "base64_encoded_image...",
  "timestamp": "1234567890",
  "config": "{\"roi_polygon\": [...], \"homography_matrix\": [...], \"fps\": 30.0}"
}
```

**Producer**: Airflow `produce_frames` task  
**Consumer**: Airflow `process_frames` task

---

### Stream: `processed-frames`

**Purpose**: Processed frames with detection/tracking results

**Consumer Group**: `redis-consumer-group`

**Message Format**:
```json
{
  "video_id": "1",
  "frame_number": "42",
  "timestamp": "1234567890",
  "processed_frame": "base64_jpeg...",
  "vehicles": "[{\"track_id\": 5, \"speed\": 75, ...}, ...]",
  "stats": "{\"total_vehicles\": 123, \"speeding_count\": 1, \"current_in_roi\": 8}",
  "roi_polygon": "[[100, 200], [300, 200], ...]",
  "has_homography": "true",
  "has_camera_matrix": "false",
  "end_of_stream": "false",
  "error": ""
}
```

**Producer**: Spark `FrameProcessor`  
**Consumer**: `redis_consumer.py` service

---

### Redis Cache Keys

#### Subscription Cache
```
websocket:subscription:video:{video_id}
  Value: "true"
  TTL: 300 seconds
  Purpose: Track if anyone is subscribed to frame channel
```

#### Analytics Cache
```
websocket:analytics:video:{video_id}
  Value: "true"
  TTL: 300 seconds
  Purpose: Track if anyone is subscribed to analytics channel
```

#### Analytics State
```
analytics:video:{video_id}
  Value: {
    "total_vehicles_count": 123,
    "current_vehicle_count": 8,
    "updated_at": 1234567890
  }
  TTL: 3600 seconds
  Purpose: Real-time analytics cache
```

---

## ⚡ Performance Optimization

### 1. Redis Consumer Optimization
- **Subscription Checking**: Only forwards frames if subscribers exist
- **Channel Separation**: Frame and analytics data routed independently
- **Cache TTL**: 5-minute TTL on subscription cache
- **Result**: Reduced network traffic by ~80% when no subscribers

### 2. Frontend Optimization
- **Append-Only List**: Speeding vehicles never re-render entire list
- **TrackBy Function**: Angular only updates changed items
- **Dual Subscriptions**: Frame and analytics updates don't interfere
- **Canvas Optimization**: Only ROI redrawn, no bounding box updates
- **Result**: Eliminated scroll jitter, smooth UX at 30 FPS

### 3. Spark Processing Optimization
- **TensorRT Acceleration**: YOLOv8 optimized with TensorRT
- **Frame-by-Frame Processing**: Real-time streaming without batching
- **ROI Pre-filtering**: Reduces tracking complexity
- **JPEG Compression**: Smaller payload sizes (30-50KB per frame)
- **Result**: 15-20 FPS processing throughput on GPU

### 4. WebSocket Optimization
- **Ping/Pong**: 30-second keepalive interval
- **Dead Client Cleanup**: Automatic removal on disconnect
- **Connection Pooling**: Reuse WebSocket connections
- **Binary Frames**: Base64 efficient for text-based WebSocket

### 5. Database Optimization
- **Batch Analytics**: Only write to DB on stream end
- **Connection Pooling**: SQLAlchemy pool (5-20 connections)
- **Indexed Queries**: Index on `video_id` foreign keys
- **JSONB Storage**: Efficient storage for nested data

---

## 🚀 Deployment

### Docker Compose Services

```yaml
services:
  # Database
  postgres:
    image: postgres:15
    ports: ["5432:5432"]
    volumes: [db_data:/var/lib/postgresql/data]
    
  # Cache & Streams
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    
  # Backend API & WebSocket
  backend:
    build: ./backend
    ports: ["8686:8686"]
    depends_on: [postgres, redis]
    volumes:
      - ./video_storage:/app/video_storage
    
  # Frontend
  frontend:
    build: ./frontend
    ports: ["4200:80"]
    
  # Redis Consumer (Bridge)
  redis-consumer:
    build: ./backend
    command: python -u -m services.redis_consumer
    depends_on: [redis, backend]
    
  # Spark Processor
  spark:
    build: ./spark
    depends_on: [redis]
    volumes:
      - ./video_storage:/app/video_storage
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    
  # Airflow Scheduler
  airflow-scheduler:
    image: apache/airflow:2.8.0
    command: scheduler
    depends_on: [postgres, redis]
    volumes:
      - ./airflow/dags:/opt/airflow/dags
      - ./video_storage:/app/video_storage
    
  # Airflow Webserver
  airflow-webserver:
    image: apache/airflow:2.8.0
    command: webserver
    ports: ["8081:8080"]
    depends_on: [postgres, redis, airflow-scheduler]
```

### Environment Variables

**Backend** (`.env`):
```bash
DATABASE_URL=postgresql://user:pass@postgres:5432/video_streaming
REDIS_HOST=redis
REDIS_PORT=6379
BACKEND_URL=http://backend:8686
AIRFLOW_API_URL=http://airflow-webserver:8080/api/v1
ALLOWED_ORIGINS=http://localhost:4200,http://frontend:80
```

**Spark**:
```bash
REDIS_HOST=redis
REDIS_PORT=6379
VIDEO_STORAGE_PATH=/app/video_storage
MODEL_PATH=/app/models/yolov8s.engine
```

**Airflow**:
```bash
AIRFLOW__CORE__EXECUTOR=LocalExecutor
AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql://user:pass@postgres:5432/airflow
AIRFLOW__CORE__LOAD_EXAMPLES=False
```

---

## 🔒 Security Considerations

### WebSocket Security
- CORS validation on WebSocket connections
- Origin checking against `ALLOWED_ORIGINS`
- Connection timeout after 60 seconds of inactivity
- Rate limiting on subscription requests (future)

### API Security
- Input validation on all endpoints
- File upload size limits (500MB)
- Path traversal protection on file access
- SQL injection prevention via ORM

### Data Privacy
- Video files stored locally (not cloud)
- No PII tracking in analytics
- Temporary Redis data with TTL
- Historical data in PostgreSQL only

---

## 📈 Monitoring & Logging

### Application Logs

**Backend**:
```python
[BACKEND-FRAME-CHANNEL] ✓ Frame 42 routed to 2 clients
[BACKEND-ANALYTICS-CHANNEL] ✓ Analytics sent (speeding: 1)
[CLIENT-CHANNEL] ✅ Client subscribed to 'processed_frame_1'
```

**Redis Consumer**:
```python
[REDIS-CONSUMER] ✓ Frame 42 → frame channel
[REDIS-CONSUMER] ✓ Analytics 42 → analytics channel (speeding: 1)
[SUBSCRIPTION-CHECK] Active subscribers for videos: [1, 2]
```

**Spark Processor**:
```python
[PERFORMANCE] Frame 42 | Video 1
  Decode:           15.23ms
  Detection:        85.45ms  (12 objects)
  Tracking:         12.34ms  (8 tracks)
  Speed Estimation: 5.67ms
  Analytics:        2.10ms
  Visualization:    8.90ms
  Encode:           12.45ms
  TOTAL:           142.14ms  (7.0 FPS)
  ★ STATS: Total=123, Speeding=1, Active=8
```

### Performance Metrics

**Key Metrics**:
- Frame processing latency: ~140ms (7 FPS)
- WebSocket message size: 30-50KB per frame
- Redis stream throughput: 1000+ messages/sec
- Database write latency: <50ms
- Frontend frame rate: 15-30 FPS (network dependent)

---

## 🔧 Troubleshooting

### Common Issues

#### 1. Frontend shows no frames
**Symptoms**: WebSocket connects but no frames appear  
**Causes**:
- Redis consumer not running
- No frame subscribers cached in Redis
- WebSocket subscription not sent

**Solution**:
```bash
# Check redis-consumer logs
docker-compose logs -f redis-consumer

# Check backend logs for subscriptions
docker-compose logs -f backend | grep "CLIENT-CHANNEL"

# Restart services
docker-compose restart redis-consumer backend frontend
```

#### 2. Speeding vehicles not appearing
**Symptoms**: Analytics stats show speeding count but list empty  
**Causes**:
- Analytics channel not subscribed
- Speed threshold filter incorrect
- Frontend not appending vehicles

**Solution**:
```bash
# Check analytics channel subscription
docker-compose logs backend | grep "analytics_metrics"

# Verify analytics data being sent
docker-compose logs redis-consumer | grep "analytics channel"
```

#### 3. High latency / dropped frames
**Symptoms**: Frame rate drops below 10 FPS  
**Causes**:
- GPU not available for TensorRT
- Network congestion
- Too many subscribers

**Solution**:
```bash
# Check GPU usage
nvidia-smi

# Check Spark logs
docker-compose logs spark | grep "PERFORMANCE"

# Reduce frame rate in video config
```

---

## 📚 API Reference

### REST API Endpoints

#### Upload Video
```http
POST /api/videos/upload
Content-Type: multipart/form-data

Body:
  video: <file>
  name: "Highway Traffic"
  roi: [[100, 200], [300, 200], [300, 400], [100, 400]]
  fps: 30.0

Response: 201 Created
{
  "id": 1,
  "name": "Highway Traffic",
  "file_path": "/app/video_storage/1.mp4",
  "roi": {...},
  "fps": 30.0,
  "created_at": "2025-12-23T10:00:00Z"
}
```

#### List Videos
```http
GET /api/videos

Response: 200 OK
{
  "videos": [
    {
      "id": 1,
      "name": "Highway Traffic",
      "file_path": "/app/video_storage/1.mp4",
      "fps": 30.0,
      "created_at": "2025-12-23T10:00:00Z"
    }
  ]
}
```

#### Start Stream
```http
POST /api/videos/1/stream/start

Response: 200 OK
{
  "message": "Video streaming started",
  "video_id": 1,
  "dag_run": {
    "dag_run_id": "manual__2025-12-23T10:00:00",
    "state": "running"
  }
}
```

#### Get WebSocket Status
```http
GET /api/websocket/status

Response: 200 OK
{
  "channels": {
    "processed_frame_1": {
      "subscriber_count": 2,
      "video_id": 1
    },
    "analytics_metrics_1": {
      "subscriber_count": 2,
      "video_id": 1
    }
  },
  "total_clients": 4,
  "active_streams": [1]
}
```

---

## 🎓 Development Guide

### Local Development Setup

1. **Clone Repository**
```bash
git clone <repository_url>
cd BDataFinalProject
```

2. **Install Dependencies**
```bash
# Backend
cd backend
pip install -r requirements.txt

# Frontend
cd frontend
npm install

# Spark
cd spark
pip install -r requirements.txt
```

3. **Start Services**
```bash
docker-compose up -d postgres redis
docker-compose up backend frontend spark redis-consumer
```

4. **Access Applications**
- Frontend: http://localhost:4200
- Backend API: http://localhost:8686
- Airflow UI: http://localhost:8081

### Adding New Features

#### Add New WebSocket Channel
1. Create handler in `backend/handlers/websocket_routing.py`
2. Register route in `Application.__init__()`
3. Update `redis_consumer.py` to route data
4. Add frontend subscription in `websocket.service.ts`

#### Add New Analytics Metric
1. Update `VehicleAnalyticsTracker.get_frame_stats()`
2. Add field to `FrameStats` interface
3. Display in `VideoDetailComponent`

---

## 📝 License & Credits

**System**: Real-Time Traffic Monitoring System  
**Version**: 2.0  
**Last Updated**: December 23, 2025  

**Technologies**:
- YOLOv8: Ultralytics
- DeepSORT: nwojke/deep_sort
- Angular: Google
- Tornado: Facebook
- Apache Airflow: Apache Software Foundation

---

## 🔗 Related Documentation

- [REDIS_MIGRATION.md](REDIS_MIGRATION.md) - Redis Streams migration guide
- [TRACKING_OPTIMIZATION.md](TRACKING_OPTIMIZATION.md) - Performance optimization details
- [SPEED_ESTIMATION_FIX.md](SPEED_ESTIMATION_FIX.md) - Speed calculation improvements
- [NEW_REQUIREMENT.md](NEW_REQUIREMENT.md) - Feature requirements specification

---

**End of System Architecture Documentation**
