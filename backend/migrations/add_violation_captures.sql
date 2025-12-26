-- ============================================================================
-- Speed Violation Captures Table
-- Stores captured frames and metadata when vehicles exceed speed limit
-- ============================================================================

-- Create the main violation captures table
CREATE TABLE IF NOT EXISTS violation_captures (
    id SERIAL PRIMARY KEY,
    video_id INTEGER NOT NULL REFERENCES video(id) ON DELETE CASCADE,
    
    -- Vehicle identification
    track_id INTEGER NOT NULL,
    
    -- Speed violation data
    speed FLOAT NOT NULL,                    -- Actual speed (km/h)
    speed_limit FLOAT NOT NULL DEFAULT 60.0, -- Speed limit threshold (km/h)
    speed_excess FLOAT NOT NULL,             -- Amount over limit (speed - speed_limit)
    
    -- Vehicle classification
    vehicle_type VARCHAR(50) NOT NULL,       -- 'car', 'truck', 'bus', 'motorcycle', 'unknown'
    class_id INTEGER NOT NULL,               -- YOLO class ID
    confidence FLOAT,                        -- Detection confidence (0.0 - 1.0)
    
    -- Frame capture data
    frame_number INTEGER NOT NULL,
    frame_image_path VARCHAR(500) NOT NULL,  -- Relative path to captured JPEG image
    thumbnail_path VARCHAR(500),             -- Relative path to thumbnail image
    
    -- Bounding box coordinates (for highlighting vehicle in captured frame)
    bbox_x1 INTEGER,
    bbox_y1 INTEGER,
    bbox_x2 INTEGER,
    bbox_y2 INTEGER,
    
    -- Timestamps
    violation_timestamp TIMESTAMP NOT NULL,  -- When the violation occurred
    video_timestamp FLOAT,                   -- Timestamp within the video (seconds)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Session tracking (links to processing session)
    session_start TIMESTAMP,
    
    -- Prevent duplicate captures for same vehicle in same frame
    CONSTRAINT unique_violation_capture UNIQUE (video_id, track_id, session_start)
);

-- ============================================================================
-- Performance Indexes
-- ============================================================================

-- Primary lookup by video
CREATE INDEX IF NOT EXISTS idx_violation_captures_video_id 
    ON violation_captures(video_id);

-- Time-based queries (recent violations, date range filters)
CREATE INDEX IF NOT EXISTS idx_violation_captures_timestamp 
    ON violation_captures(violation_timestamp DESC);

-- Speed filtering (sort by severity)
CREATE INDEX IF NOT EXISTS idx_violation_captures_speed 
    ON violation_captures(speed DESC);

-- Vehicle type filtering
CREATE INDEX IF NOT EXISTS idx_violation_captures_vehicle_type 
    ON violation_captures(vehicle_type);

-- Session-based queries (get all violations from a session)
CREATE INDEX IF NOT EXISTS idx_violation_captures_session 
    ON violation_captures(video_id, session_start);

-- Composite index for common dashboard query
CREATE INDEX IF NOT EXISTS idx_violation_captures_dashboard 
    ON violation_captures(video_id, violation_timestamp DESC, speed DESC);

-- ============================================================================
-- Comments for Documentation
-- ============================================================================

COMMENT ON TABLE violation_captures IS 
    'Captured frames and metadata for speed violations detected during video processing';

COMMENT ON COLUMN violation_captures.frame_image_path IS 
    'Relative path to full-resolution JPEG capture (from VIOLATION_CAPTURES_DIR)';

COMMENT ON COLUMN violation_captures.thumbnail_path IS 
    'Relative path to thumbnail image for grid display (320x180)';

COMMENT ON COLUMN violation_captures.speed_excess IS 
    'Calculated as: speed - speed_limit. Always positive for violations.';

COMMENT ON COLUMN violation_captures.session_start IS 
    'Links violation to specific video processing session for grouping';

-- ============================================================================
-- Sample Queries for Reference
-- ============================================================================

-- Get all violations for a video session (most recent first)
-- SELECT * FROM violation_captures 
-- WHERE video_id = 1 AND session_start = '2025-01-01 12:00:00'
-- ORDER BY violation_timestamp DESC;

-- Get violation statistics by vehicle type
-- SELECT vehicle_type, COUNT(*) as count, AVG(speed) as avg_speed, MAX(speed) as max_speed
-- FROM violation_captures
-- WHERE video_id = 1
-- GROUP BY vehicle_type;

-- Get speed distribution
-- SELECT 
--     CASE 
--         WHEN speed >= 60 AND speed < 70 THEN '60-70'
--         WHEN speed >= 70 AND speed < 80 THEN '70-80'
--         WHEN speed >= 80 AND speed < 90 THEN '80-90'
--         WHEN speed >= 90 AND speed < 100 THEN '90-100'
--         ELSE '100+'
--     END as speed_range,
--     COUNT(*) as count
-- FROM violation_captures
-- GROUP BY speed_range
-- ORDER BY speed_range;
