# SYSTEM UPDATE SPECIFICATIONS (VIDEO MANAGEMENT SYSTEM)

## 1. Context & Objective
The goal is to update the existing Video Management System with focus on UI improvements, WebSocket efficiency, and Data Engineering optimization.
**Role:** Act as a Senior Full-Stack Developer.
**Constraint:** Do NOT modify existing API response formats unless explicitly stated.

---

## 2. Feature Requirements

### A. UI: Video Management (Dashboard)
**Current Status:** The main UI loads all stored videos but lacks deletion capability.
**Requirement:**
- Implement a **"Delete Video"** button/icon for each video item in the main list.
- **Backend:** Ensure the API handles physical file deletion and database record removal.
- **Frontend:** Update the UI state immediately after deletion without requiring a full page refresh.

### B. UI: Video Detail View (Clean Up)
**Current Status:** The UI displays technical debug info (`ROI`, `File Path`, `Calibrate Coordinates`) which is cluttered.
**Requirement:**
- **Hide** these fields from the User Interface.
- **Note:** Keep the data in the API response (do not strip it from backend), just hide it visually on the Frontend.

---

### C. WebSocket Logic & Optimization (Critical)

#### 1. Frontend (Client-side)
* **Subscription Management:**
    * **On Click:** When a user clicks a video, immediately `subscribe` to that specific video's WebSocket channel.
    * **On Switch:** If switching between videos, immediately `unsubscribe` from the old channel and `subscribe` to the new one. Ensure strict 1-to-1 subscription to prevent data leaks or overlaps.
* **Watchdog / Timeout Mechanism:**
    * Implement a **3-second timer**.
    * **Logic:** If the client is subscribed but receives **NO data** for > 3 seconds:
        * Revert the video player to the **Default Thumbnail**.
        * Reset the **"Start Stream"** button to its default (inactive/ready) state.

#### 2. Backend (Server-side)
* **Routing Optimization:**
    * In the `websocket_routing` (or broadcast logic), check for active subscribers before sending data.
    * **Logic:** `If (active_subscribers_on_channel == 0) { return; // Stop processing }`.
    * **Goal:** Prevent server resource waste when no one is watching.

---

### D. Analytics & Data Engineering (Redis vs DB)

**Goal:** Track vehicle statistics without bottlenecking the main SQL Database during high-frequency video processing.

#### 1. Metrics to Track
Add the following fields/logic to the processing pipeline:
- `total_vehicles_count`: Cumulative number of vehicles that have entered the ROI.
- `current_vehicles_count`: Number of vehicles currently inside the ROI.
- `vehicle_dwell_time`: Duration (timestamp) each vehicle stays in the ROI.
- `vehicle_type`: Classification of the vehicle.

#### 2. Write Strategy (Pipeline)
* **Phase 1 (Real-time):** Write all the above metrics to **Redis** (In-memory cache) while the video is processing/streaming. Do NOT write to SQL DB on every frame/event.
* **Phase 2 (Completion):** Only when the video processing is **fully finished**, trigger a batch job to dump the aggregated data from Redis to the **SQL Database**.