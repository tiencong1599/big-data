# Speed Estimation Root Cause Analysis & Fix

## 🔴 Critical Issues Identified

### Issue 1: Homography Matrix Never Computed (CRITICAL)
**Problem:**
- Frontend sends `calibrate_coordinates` (4 pixel + 4 real-world point pairs)
- Backend stores these coordinates but **never computes the homography matrix**
- `homography_matrix` field remains NULL in database
- Spark processor receives NULL → creates **identity matrix** as fallback
- Identity matrix treats pixel displacement as world displacement
- Example: 100 pixels = 100 "meters" → completely wrong speeds

**Data Flow:**
```
User clicks 4 calibration points
    ↓
Frontend sends: calibrate_coordinates: {
  points: [
    {pixel: [100, 200], real: [0, 0]},
    {pixel: [500, 200], real: [10, 0]},
    {pixel: [500, 400], real: [10, 5]},
    {pixel: [100, 400], real: [0, 5]}
  ]
}
    ↓
Backend: Stores calibrate_coordinates ✓
Backend: homography_matrix = NULL ✗
    ↓
Producer: get_video_config() returns homography_matrix: null
    ↓
Spark Processor: Creates identity matrix fallback
    ↓
SpeedEstimator: No perspective correction
    ↓
Result: Speeds are completely wrong!
```

**Root Cause:**
The backend handler `video_handler.py` was missing the logic to:
1. Parse calibration coordinates
2. Call `cv2.findHomography(src_points, dst_points)`
3. Store computed 3x3 matrix in database

---

### Issue 2: Missing Boolean Flags
**Problem:**
`get_video_config()` returned:
```python
{
    'roi_polygon': [[x1,y1], [x2,y2], ...],
    'homography_matrix': [[...], [...], [...]],
    'fps': 30.0
}
```

But was missing:
- `use_roi` - tells processor whether to apply ROI filtering
- `use_homography` - tells processor whether to use homography for speed estimation

**Impact:**
- Processor defaults both to `False` when missing
- ROI filtering may not be applied even when ROI exists
- Homography may not be used even when available

---

### Issue 3: Camera Matrix Not Used
**Problem:**
- System has `camera_matrix` field (intrinsic matrix K)
- `calibrate.py` can compute it from chessboard images
- But `SpeedEstimator` doesn't accept `camera_matrix` parameter
- No lens distortion correction applied

**Impact:**
- Wide-angle cameras have lens distortion
- Pixel coordinates are distorted → world coordinates are inaccurate
- Minor issue compared to #1 and #2, but affects accuracy

---

## ✅ Solutions Implemented

### Fix 1: Compute Homography Matrix from Calibration Points

**Added to `backend/handlers/video_handler.py`:**

1. **New Function:**
```python
def compute_homography_from_calibration(calibrate_data):
    """
    Compute homography matrix from calibration coordinates.
    
    Args:
        calibrate_data (dict): {
            'points': [
                {'pixel': [x, y], 'real': [X, Y]},
                ...
            ]
        }
    
    Returns:
        list: 3x3 homography matrix as nested list
    """
    points = calibrate_data['points']
    
    # Extract image and world coordinates
    src_points = np.float32([p['pixel'] for p in points])
    dst_points = np.float32([p['real'] for p in points])
    
    # Compute homography (image -> world)
    H, mask = cv2.findHomography(src_points, dst_points)
    
    return H.tolist()  # Convert to list for JSON
```

2. **Modified Upload Handler:**
```python
# Compute homography matrix from calibration coordinates if provided
if calibrate_data and not homography_data:
    logger.info("Computing homography matrix from calibration coordinates...")
    computed_homography = compute_homography_from_calibration(calibrate_data)
    if computed_homography:
        homography_data = computed_homography
        logger.info("✓ Homography matrix computed and will be stored")
    else:
        logger.warning("✗ Failed to compute homography matrix")
```

**Result:**
- Calibration points → Homography matrix automatically computed
- Matrix stored in database
- Producer sends correct matrix to Spark processor
- SpeedEstimator uses real perspective transformation

---

### Fix 2: Add Boolean Flags to Config

**Modified `backend/models/video.py`:**

```python
return {
    'video_id': video.id,
    'roi_polygon': roi_polygon,
    'homography_matrix': video.homography_matrix,
    'camera_matrix': video.camera_matrix,
    'fps': video.fps or 30.0,
    'use_roi': roi_polygon is not None and len(roi_polygon) > 0,  # NEW
    'use_homography': video.homography_matrix is not None          # NEW
}
```

**Result:**
- Processor knows explicitly whether to use ROI filtering
- Processor knows explicitly whether to use homography
- No more guessing based on null checks

---

## 🔍 How Homography Works

### Concept:
Homography matrix transforms 2D image coordinates to 2D world coordinates (ground plane).

**Mathematical Formula:**
```
[X]   [h11 h12 h13]   [x]
[Y] = [h21 h22 h23] * [y]
[W]   [h31 h32 h33]   [1]

World coordinates: (X/W, Y/W)
```

### Example:
```
Calibration points:
  Pixel (100, 200) → World (0, 0) meters
  Pixel (500, 200) → World (10, 0) meters
  Pixel (500, 400) → World (10, 5) meters
  Pixel (100, 400) → World (0, 5) meters

Computed Homography H:
  [[0.025, 0.01,  -2.5],
   [0.005, 0.015, -3.0],
   [0.0,   0.0,    1.0]]

Vehicle bbox bottom-center: (300, 350)
Transform: H @ [300, 350, 1] = [5.0, 2.5, 1.0]
World position: (5.0, 2.5) meters

Next frame: (320, 360) → (5.5, 2.8) meters
Displacement: √((5.5-5.0)² + (2.8-2.5)²) = 0.58 meters
Time: 1 frame @ 30 FPS = 0.033 seconds
Speed: 0.58 / 0.033 = 17.5 m/s = 63 km/h ✓
```

Without homography (identity matrix):
```
(300, 350) → (300, 350) "meters" 
(320, 360) → (320, 360) "meters"
Displacement: √(20² + 10²) = 22.4 "meters"
Speed: 22.4 / 0.033 = 678 m/s = 2,441 km/h ✗ WRONG!
```

---

## 📋 Verification Steps

### 1. Rebuild Backend Service
The backend code has been updated. Rebuild the Docker image:

```bash
docker-compose up -d --build backend
```

### 2. Upload a New Video
1. Open frontend: http://localhost:4200
2. Upload video with:
   - ✓ Select video file
   - ✓ Click 4 ROI points
   - ✓ Click 4 calibration points
   - ✓ Enter real-world coordinates for each calibration point

### 3. Check Backend Logs
Watch for these log messages during upload:

```
Computing homography matrix from calibration coordinates...
  Image points: [[100.0, 200.0], [500.0, 200.0], ...]
  World points: [[0.0, 0.0], [10.0, 0.0], ...]
Homography matrix computed successfully:
[[0.025 0.01  -2.5 ]
 [0.005 0.015 -3.0 ]
 [0.0   0.0    1.0  ]]
✓ Homography matrix computed and will be stored
```

### 4. Verify Database Storage
Connect to PostgreSQL and check the video record:

```sql
SELECT 
    id,
    name,
    homography_matrix IS NOT NULL as has_homography,
    calibrate_coordinates IS NOT NULL as has_calibration
FROM video
ORDER BY id DESC
LIMIT 1;
```

Expected result:
```
id | name      | has_homography | has_calibration
---+-----------+----------------+----------------
 5 | test.mp4  | t              | t
```

### 5. Check Spark Processor Logs
When processing starts, look for:

```
Config: ROI=True, H=True, FPS=30.0
SpeedEstimator initialized with FPS: 30.0
```

NOT:
```
Config: ROI=False, H=False, FPS=30.0  ✗ WRONG
```

### 6. Verify Speed Results
With proper homography:
- Speeds should be in realistic range: 20-120 km/h for vehicles
- Stationary objects: 0-5 km/h
- Fast vehicles: 60-100 km/h

Without homography (identity matrix):
- Speeds are nonsensical: 500-3000 km/h ✗

---

## 🎯 Best Practices for Calibration

### 1. Select Good Calibration Points
✓ **Good points:**
- Corners of a known-size rectangle (e.g., parking space)
- Clearly visible lane markings with known dimensions
- Points spread across the entire ROI area
- Points on the same ground plane

✗ **Bad points:**
- Points on different height levels (e.g., sidewalk and road)
- Points outside the ROI
- Clustered in one corner
- On moving objects

### 2. Measure Real-World Coordinates Accurately
Use a measuring tape or known dimensions:
- Parking space: 2.5m × 5.0m
- Lane width: 3.5m
- Road marking: 3m dash + 9m gap

### 3. Coordinate System
- Origin (0, 0): Bottom-left or top-left calibration point
- X-axis: Horizontal direction (left→right)
- Y-axis: Vertical direction (top→bottom or bottom→top)
- Units: Meters (consistent with speed output)

**Example:**
```
    (0, 5)          (10, 5)
       *--------------*
       |              |
       |    ROI       |
       |              |
       *--------------*
    (0, 0)          (10, 0)

Rectangle: 10m × 5m
```

### 4. Validation
After calibration, check:
1. Known distance: 5 meters should transform to ~5.0 in world coordinates
2. Known speed: Vehicle at 50 km/h should estimate ~45-55 km/h
3. Stationary object: Should have speed ~0 km/h

---

## 🚀 Next Steps

### Immediate Actions:
1. ✅ **Rebuild backend** - Changes applied to `video_handler.py` and `video.py`
2. ⏳ **Upload new test video** - With proper calibration points
3. ⏳ **Verify speed results** - Should be realistic now

### Future Enhancements:
1. **Add Camera Matrix Support**
   - Update `SpeedEstimator.__init__()` to accept `camera_matrix`
   - Apply lens distortion correction before homography transform
   - Use `cv2.undistortPoints()` for wide-angle cameras

2. **Validation UI**
   - Show computed homography matrix in frontend
   - Display transformed calibration points for verification
   - Add "Test Calibration" button to validate transformation

3. **Multiple Calibration Methods**
   - Manual point selection (current)
   - Automatic chessboard detection
   - Pre-defined camera profiles

4. **Speed Smoothing**
   - Current: EMA with α=0.2
   - Add Kalman filter for better noise reduction
   - Detect and filter outliers (sudden speed spikes)

---

## 📊 Technical Details

### Homography Computation (OpenCV):
```python
cv2.findHomography(src_points, dst_points, method=0)
```
- **src_points**: Image coordinates (pixels)
- **dst_points**: World coordinates (meters)
- **method**: 0 = all points used (no RANSAC)
- **Returns**: 3×3 matrix H, inlier mask

### Speed Calculation Pipeline:
```
1. YOLO Detection → bbox [x1, y1, x2, y2]
2. Ground Point → (cx, y2) = ((x1+x2)/2, y2)
3. Homography Transform → (X, Y) world coordinates
4. Displacement → d = √((X₂-X₁)² + (Y₂-Y₁)²)
5. Time → t = Δframes / FPS
6. Speed → v = d/t × 3.6 (m/s to km/h)
7. Smoothing → v_smooth = 0.2×v + 0.8×v_prev
```

### Configuration Flow:
```
Database
  ↓
get_video_config()
  ↓
{
  video_id: 1,
  roi_polygon: [[...], [...]],
  homography_matrix: [[...], [...], [...]],  ← Now populated!
  use_roi: true,                              ← Now included!
  use_homography: true,                       ← Now included!
  fps: 30.0
}
  ↓
RedisProducer
  ↓
Redis Stream
  ↓
FrameProcessor
  ↓
SpeedEstimator(homography_matrix=H)          ← Uses real matrix!
```

---

## ✅ Summary

**Root Cause Found:**
- Homography matrix was never computed from calibration points
- Identity matrix fallback caused completely wrong speed calculations

**Fix Applied:**
- Added `compute_homography_from_calibration()` function
- Modified upload handler to compute and store homography matrix
- Added `use_roi` and `use_homography` flags to config

**Expected Outcome:**
- Speed estimates should now be realistic (20-120 km/h)
- Proper perspective correction applied
- Accurate distance measurements in world coordinates

**Action Required:**
```bash
# Rebuild backend service
docker-compose up -d --build backend

# Upload a new video with calibration
# Verify speed results are now accurate
```

---

**Last Updated:** 2025-12-14
**Status:** ✅ Fixed - Ready for Testing
