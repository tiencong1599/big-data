# 🚨 Speed Violation Capture & Storage Feature - Implementation Plan

## 📋 Executive Summary

This document outlines the implementation plan for a new **Speed Violation Capture System** that will:
1. **Capture frame images** when vehicles exceed the speed limit
2. **Store violation metadata** (time, speed, vehicle type, red bounding box for violated vehicle,etc.)
3. **Provide a dedicated UI** for viewing and managing violations

---

## 🎯 Feature Requirements

### Functional Requirements
| Requirement | Description |
|-------------|-------------|
| **Frame Capture** | Capture and store the video frame when a vehicle exceeds speed limit |
| **Violation Metadata** | Store: timestamp, speed limit, actual speed, red bounding box for violated vehicle,, video_id, vehicle type, track_id, confidence |
| **Image Storage** | Store captured frames as JPEG files with unique identifiers |
| **UI Dashboard** | New "Speed Violation Stats Storage" page to view all violations |
| **Filtering** | Filter violations by video, date range, vehicle type, speed range |
| **Export** | Export violation data as CSV/JSON with images |

### Non-Functional Requirements
| Requirement | Target |
|-------------|--------|
| **Performance** | Maintain current ~14 FPS processing speed |
| **Storage** | Efficient image compression (< 50KB per capture) |
| **Latency** | < 10ms additional overhead per violation capture |
| **Scalability** | Handle 1000+ violations per video session |

---

## 🏗️ Architecture Overview

### Current vs. Proposed Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CURRENT FLOW (No Changes)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Video → Spark Processor → Detection → Tracking → Speed Estimation          │
│                                          ↓                                   │
│                                   Redis Streams                              │
│                                          ↓                                   │
│                              Backend → WebSocket → Frontend                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                        NEW FLOW (With Violation Capture)                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Video → Spark Processor → Detection → Tracking → Speed Estimation          │
│                                          ↓                                   │
│                              ┌──────────┴──────────┐                        │
│                              ↓                     ↓                        │
│                     Speed > Limit?            Normal Flow                   │
│                              ↓                     ↓                        │
│                    ┌─────────┴─────────┐    Redis Streams                   │
│                    ↓                   ↓          ↓                         │
│             Capture Frame      Create Violation   │                         │
│                    ↓           Metadata           │                         │
│             Save to Disk            ↓             │                         │
│             (Async I/O)       Buffer in Memory    │                         │
│                    ↓                ↓             │                         │
│                    └────────┬───────┘             │                         │
│                             ↓                     ↓                         │
│                      Batch Insert          Backend WebSocket                │
│                      (Every 10 records)          ↓                          │
│                             ↓              Frontend UI                      │
│                       PostgreSQL                                            │
│                             ↓                                               │
│                    violation_captures                                       │
│                         table                                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Component Changes Summary

### Files to CREATE (New)

| File | Purpose |
|------|---------|
| `backend/migrations/add_violation_captures.sql` | Database migration for new table |
| `backend/handlers/violation_handler.py` | REST API endpoints for violations |
| `spark/violation_capture_handler.py` | Frame capture & async processing |
| `frontend/src/app/models/violation.model.ts` | TypeScript interfaces |
| `frontend/src/app/services/violation.service.ts` | API service |
| `frontend/src/app/components/violation-dashboard/*` | UI component |

### Files to MODIFY (Existing)

| File | Changes |
|------|---------|
| `backend/models/video.py` | Add `ViolationCapture` SQLAlchemy model |
| `backend/app.py` | Register new API routes |
| `spark/video_frame_processor.py` | Integrate violation capture logic |
| `spark/redis_frame_processor.py` | Integrate violation capture logic |
| `frontend/src/app/app.routes.ts` | Add `/violations` route |
| `frontend/src/app/app.component.html` | Add navigation link |
| `docker-compose.yml` | Add volume for violation captures |

---

## 📁 Database Schema

### New Table: `violation_captures`

```sql
CREATE TABLE IF NOT EXISTS violation_captures (
    id SERIAL PRIMARY KEY,
    video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    
    -- Vehicle identification
    track_id INTEGER NOT NULL,
    
    -- Speed violation data
    speed FLOAT NOT NULL,                    -- Actual speed (km/h)
    speed_limit FLOAT NOT NULL DEFAULT 60.0, -- Speed limit (km/h)
    speed_excess FLOAT NOT NULL,             -- How much over limit (km/h)
    
    -- Vehicle classification
    vehicle_type VARCHAR(50) NOT NULL,       -- 'car', 'truck', 'bus', 'motorcycle'
    class_id INTEGER NOT NULL,
    confidence FLOAT,
    
    -- Frame capture data
    frame_number INTEGER NOT NULL,
    frame_image_path VARCHAR(500) NOT NULL,  -- Path to captured image
    thumbnail_path VARCHAR(500),             -- Smaller preview image
    
    -- Bounding box (for highlighting vehicle in image)
    bbox_x1 INTEGER,
    bbox_y1 INTEGER,
    bbox_x2 INTEGER,
    bbox_y2 INTEGER,
    
    -- Timestamps
    violation_timestamp TIMESTAMP NOT NULL,  -- When violation occurred
    video_timestamp FLOAT,                   -- Frame timestamp in video
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    session_start TIMESTAMP,
    
    -- Prevent duplicate captures
    CONSTRAINT unique_violation UNIQUE (video_id, track_id, frame_number)
);

-- Performance indexes
CREATE INDEX idx_violations_video_id ON violation_captures(video_id);
CREATE INDEX idx_violations_timestamp ON violation_captures(violation_timestamp);
CREATE INDEX idx_violations_speed ON violation_captures(speed);
CREATE INDEX idx_violations_vehicle_type ON violation_captures(vehicle_type);
CREATE INDEX idx_violations_session ON violation_captures(video_id, session_start);
```

---

## ⚡ Performance Analysis & Optimization

### Potential Bottlenecks Identified

| Component | Risk Level | Bottleneck Description | Mitigation Strategy |
|-----------|------------|------------------------|---------------------|
| **Frame Capture I/O** | 🔴 HIGH | Disk write blocks main processing thread | Background thread + async queue |
| **Image Encoding** | 🟡 MEDIUM | JPEG encoding uses CPU cycles | Optimized quality (85%) + background thread |
| **Database Inserts** | 🟡 MEDIUM | Per-violation INSERT causes overhead | Batch inserts (every 10 records) |
| **Memory Usage** | 🟡 MEDIUM | Frame copies consume RAM | Queue size limit (100) + immediate compression |
| **Duplicate Captures** | 🟢 LOW | Same vehicle captured multiple times | Track-based deduplication (O(1) lookup) |
| **Frontend Loading** | 🟢 LOW | Loading many violation images | Thumbnails + lazy loading + pagination |

### Performance Safeguards

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    PERFORMANCE PROTECTION MEASURES                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. ASYNC PROCESSING (Prevents FPS drop)                                 │
│     ├── Frame capture runs in dedicated background thread                │
│     ├── Main processing loop NEVER blocked                               │
│     ├── Queue-based decoupling (max 100 pending items)                   │
│     └── Expected overhead: < 1ms per violation check                     │
│                                                                          │
│  2. DEDUPLICATION (Prevents storage explosion)                           │
│     ├── Only FIRST violation per track_id captured per session           │
│     ├── Set-based lookup: O(1) time complexity                           │
│     ├── Memory: ~8 bytes per tracked vehicle                             │
│     └── Example: 200 vehicles = 1.6KB memory                             │
│                                                                          │
│  3. BATCH DATABASE OPERATIONS (Reduces DB load)                          │
│     ├── Accumulate violations in memory buffer                           │
│     ├── Bulk INSERT every 10 records OR on session end                   │
│     ├── Reduces DB round-trips by 10x                                    │
│     └── Transaction-safe with rollback on error                          │
│                                                                          │
│  4. IMAGE OPTIMIZATION (Reduces storage & I/O)                           │
│     ├── JPEG quality: 85% (visually lossless)                            │
│     ├── Full image: ~40-50KB per capture                                 │
│     ├── Thumbnail: 320x180 @ 70% quality (~5KB)                          │
│     └── Storage estimate: 1000 violations ≈ 50MB                         │
│                                                                          │
│  5. QUEUE OVERFLOW PROTECTION (Prevents memory explosion)                │
│     ├── Maximum queue size: 100 pending captures                         │
│     ├── If queue full: Skip capture (log warning, don't crash)           │
│     ├── Graceful degradation under extreme load                          │
│     └── Monitoring: Log queue depth every 100 frames                     │
│                                                                          │
│  6. FRONTEND OPTIMIZATION (Smooth UI)                                    │
│     ├── Thumbnails for grid view (5KB vs 50KB)                           │
│     ├── Lazy loading with Intersection Observer                          │
│     ├── Pagination: 20 items per page default                            │
│     └── Virtual scrolling for 1000+ violations                           │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Expected Performance Impact

| Metric | Before | After | Impact |
|--------|--------|-------|--------|
| **Processing FPS** | 14 FPS | 13.5-14 FPS | < 5% reduction |
| **Memory Usage** | ~2GB | ~2.1GB | +100MB (queue + buffers) |
| **CPU Usage** | 60% | 62% | +2% (background encoding) |
| **Disk I/O** | Minimal | +50KB/violation | Async, non-blocking |

---

## 🔧 Implementation Tasks

### Phase 1: Database & Backend (Priority: HIGH)

| # | Task | Estimated Time | Dependencies |
|---|------|----------------|--------------|
| 1.1 | Create database migration SQL | 30 min | None |
| 1.2 | Add `ViolationCapture` model to `models/video.py` | 30 min | 1.1 |
| 1.3 | Create `violation_handler.py` with REST endpoints | 2 hours | 1.2 |
| 1.4 | Register routes in `app.py` | 15 min | 1.3 |
| 1.5 | Add violation captures volume to `docker-compose.yml` | 15 min | None |
| 1.6 | Test API endpoints with Postman/curl | 30 min | 1.4 |

### Phase 2: Spark Processor Integration (Priority: HIGH)

| # | Task | Estimated Time | Dependencies |
|---|------|----------------|--------------|
| 2.1 | Create `violation_capture_handler.py` | 2 hours | None |
| 2.2 | Integrate handler into `redis_frame_processor.py` | 1 hour | 2.1 |
| 2.3 | Add batch insert logic to analytics persistence | 1 hour | 2.1, 1.2 |
| 2.4 | Test violation capture with sample video | 1 hour | 2.2, 2.3 |
| 2.5 | Performance benchmarking (before/after FPS) | 30 min | 2.4 |

### Phase 3: Frontend UI (Priority: MEDIUM)

| # | Task | Estimated Time | Dependencies |
|---|------|----------------|--------------|
| 3.1 | Create `violation.model.ts` interfaces | 15 min | None |
| 3.2 | Create `violation.service.ts` API service | 45 min | 3.1 |
| 3.3 | Create `violation-dashboard` component (TS) | 2 hours | 3.2 |
| 3.4 | Create `violation-dashboard` template (HTML) | 2 hours | 3.3 |
| 3.5 | Create `violation-dashboard` styles (CSS) | 1 hour | 3.4 |
| 3.6 | Add route and navigation link | 15 min | 3.5 |
| 3.7 | Test UI with mock data | 30 min | 3.6 |
| 3.8 | Integration test with real violations | 30 min | 3.7, 2.4 |

### Phase 4: Polish & Documentation (Priority: LOW)

| # | Task | Estimated Time | Dependencies |
|---|------|----------------|--------------|
| 4.1 | Add loading states and error handling | 30 min | 3.8 |
| 4.2 | Implement CSV/JSON export | 30 min | 3.8 |
| 4.3 | Add image modal with full details | 30 min | 3.8 |
| 4.4 | Update README with new feature | 30 min | All |
| 4.5 | End-to-end testing | 1 hour | All |

### Total Estimated Time: ~18 hours

---

## 📂 Directory Structure (After Implementation)

```
BDataFinalProject/
├── backend/
│   ├── handlers/
│   │   ├── violation_handler.py      # NEW: REST API endpoints
│   │   └── ... (existing)
│   ├── migrations/
│   │   ├── add_violation_captures.sql # NEW: Database migration
│   │   └── ... (existing)
│   ├── models/
│   │   └── video.py                   # MODIFIED: Add ViolationCapture model
│   └── app.py                         # MODIFIED: Register new routes
│
├── spark/
│   ├── violation_capture_handler.py   # NEW: Async capture handler
│   ├── redis_frame_processor.py       # MODIFIED: Integrate capture
│   └── ... (existing)
│
├── frontend/src/app/
│   ├── models/
│   │   └── violation.model.ts         # NEW: TypeScript interfaces
│   ├── services/
│   │   └── violation.service.ts       # NEW: API service
│   ├── components/
│   │   └── violation-dashboard/       # NEW: UI component
│   │       ├── violation-dashboard.component.ts
│   │       ├── violation-dashboard.component.html
│   │       └── violation-dashboard.component.css
│   └── app.routes.ts                  # MODIFIED: Add route
│
├── violation_captures/                # NEW: Image storage directory
│   └── {video_id}/
│       └── {date}/
│           ├── violation_{video_id}_{track_id}_{frame}.jpg
│           └── thumb_{video_id}_{track_id}_{frame}.jpg
│
└── docker-compose.yml                 # MODIFIED: Add volume mount
```

---

## 🔌 API Endpoints

### Violation Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/violations` | List violations with filtering & pagination |
| `GET` | `/api/violations/{id}` | Get single violation details |
| `GET` | `/api/violations/stats` | Get violation statistics |
| `GET` | `/api/violations/export` | Export as CSV/JSON |
| `GET` | `/api/violations/images/{path}` | Serve violation images |
| `DELETE` | `/api/violations/{id}` | Delete violation record |

### Query Parameters for `/api/violations`

| Parameter | Type | Description |
|-----------|------|-------------|
| `video_id` | int | Filter by video |
| `session_start` | datetime | Filter by session |
| `vehicle_type` | string | Filter by vehicle type |
| `min_speed` | float | Minimum speed filter |
| `max_speed` | float | Maximum speed filter |
| `date_from` | date | Start date filter |
| `date_to` | date | End date filter |
| `limit` | int | Page size (default: 50) |
| `offset` | int | Pagination offset |
| `sort_by` | string | Sort field |
| `sort_order` | asc/desc | Sort direction |

---

## 🖥️ UI Wireframe

```
┌──────────────────────────────────────────────────────────────────────────┐
│  🚨 Speed Violation Stats Storage                                         │
│  Captured violations with frame evidence                                  │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐            │
│  │   📊    │ │   🕐    │ │   🚗    │ │   🚚    │ │   🚌    │            │
│  │   156   │ │   23    │ │   89    │ │   42    │ │   25    │            │
│  │  Total  │ │ Last24h │ │  Cars   │ │ Trucks  │ │  Buses  │            │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘            │
│                                                                          │
│  Speed Distribution                                                      │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ 60-70  ████████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  45    │ │
│  │ 70-80  ██████████████████████████████░░░░░░░░░░░░░░░░░░░░  62    │ │
│  │ 80-90  ████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  32    │ │
│  │ 90-100 ██████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  12    │ │
│  │ 100+   ███░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   5    │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌─ Filters ──────────────────────────────────────────────────────────┐ │
│  │ Video: [All Videos    ▼]  Type: [All Types ▼]  Speed: [60] - [200] │ │
│  │ From:  [____________]     To:   [____________]   [Clear] [Export▼] │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐   │
│  │ [Thumbnail]  │ │ [Thumbnail]  │ │ [Thumbnail]  │ │ [Thumbnail]  │   │
│  │  ┌────────┐  │ │  ┌────────┐  │ │  ┌────────┐  │ │  ┌────────┐  │   │
│  │  │ 78km/h │  │ │  │ 92km/h │  │ │  │ 85km/h │  │ │  │105km/h │  │   │
│  │  └────────┘  │ │  └────────┘  │ │  └────────┘  │ │  └────────┘  │   │
│  │ Vehicle: Car │ │ Vehicle: Trk │ │ Vehicle: Bus │ │ Vehicle: Car │   │
│  │ Excess: +18  │ │ Excess: +32  │ │ Excess: +25  │ │ Excess: +45  │   │
│  │ 12:34:56     │ │ 12:35:12     │ │ 12:36:45     │ │ 12:37:02     │   │
│  │ Track: #42   │ │ Track: #67   │ │ Track: #89   │ │ Track: #103  │   │
│  │         [🗑️] │ │         [🗑️] │ │         [🗑️] │ │         [🗑️] │   │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘   │
│                                                                          │
│  [««] [«] Page 1 of 8 (156 total) [»] [»»]                              │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 🐳 Docker Changes

### docker-compose.yml additions

```yaml
services:
  spark_processor:
    volumes:
      - ./violation_captures:/app/violation_captures  # NEW
    environment:
      - VIOLATION_CAPTURES_DIR=/app/violation_captures  # NEW

  video_streaming_backend:
    volumes:
      - ./violation_captures:/app/violation_captures  # NEW (for serving images)
    environment:
      - VIOLATION_CAPTURES_DIR=/app/violation_captures  # NEW
```

---

## ✅ Acceptance Criteria

### Functional
- [ ] When vehicle speed > 60 km/h, frame is captured with bounding box annotation
- [ ] Violation metadata stored in database with all required fields
- [ ] Only first violation per vehicle (track_id) captured per session
- [ ] UI displays violations in paginated grid with thumbnails
- [ ] Clicking violation shows full image with detailed metadata
- [ ] Filters work correctly (video, type, speed range, date)
- [ ] Export produces valid CSV/JSON files
- [ ] Delete removes both database record and image files

### Performance
- [ ] FPS remains ≥ 13 FPS (< 10% degradation from ~14 FPS baseline)
- [ ] Capture queue never blocks main processing thread
- [ ] Image files < 60KB each (average ~45KB)
- [ ] UI loads 20 violations in < 500ms

### Reliability
- [ ] Queue overflow gracefully skipped (logged, not crashed)
- [ ] Database batch insert has transaction rollback on error
- [ ] Missing images handled gracefully in UI
- [ ] Violation capture continues working after session restart

---

## 🚀 Rollout Plan

1. **Development** (Week 1)
   - Implement backend (database + API)
   - Implement Spark capture handler
   - Basic testing

2. **Integration** (Week 2)
   - Integrate capture into processing pipeline
   - Performance benchmarking
   - Fix any issues

3. **Frontend** (Week 2-3)
   - Build UI components
   - Connect to API
   - Polish UX

4. **Testing & Documentation** (Week 3)
   - End-to-end testing
   - Performance validation
   - Update documentation

---

## 📝 Notes

- Speed limit is configurable (default: 60 km/h)
- Image retention policy: Consider adding cleanup job for old violations
- Future enhancement: Add violation alerts via WebSocket for real-time notification
- Future enhancement: Add license plate recognition integration

---

*Document created: December 26, 2025*
*Last updated: December 26, 2025*
