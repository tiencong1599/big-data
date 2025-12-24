-- backend/migrations/add_analytics_table.sql
-- Phase 3: Database Analytics Persistence
-- Created: 2025-12-24

-- ============================================================================
-- TABLE 1: video_analytics_snapshots
-- Purpose: Store periodic snapshots of real-time analytics (every N seconds)
-- ============================================================================
CREATE TABLE IF NOT EXISTS video_analytics_snapshots (
    id SERIAL PRIMARY KEY,
    video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    frame_number INTEGER NOT NULL,
    timestamp FLOAT NOT NULL,
    
    -- Frame-level stats
    total_vehicles INTEGER DEFAULT 0,
    speeding_count INTEGER DEFAULT 0,
    current_in_roi INTEGER DEFAULT 0,
    
    -- Session metadata
    session_start TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT unique_video_frame UNIQUE (video_id, frame_number)
);

CREATE INDEX IF NOT EXISTS idx_analytics_snapshots_video_id ON video_analytics_snapshots(video_id);
CREATE INDEX IF NOT EXISTS idx_analytics_snapshots_timestamp ON video_analytics_snapshots(timestamp);
CREATE INDEX IF NOT EXISTS idx_analytics_snapshots_session ON video_analytics_snapshots(video_id, session_start);

COMMENT ON TABLE video_analytics_snapshots IS 'Periodic snapshots of real-time analytics for trend analysis';
COMMENT ON COLUMN video_analytics_snapshots.total_vehicles IS 'Cumulative count of unique vehicles detected';
COMMENT ON COLUMN video_analytics_snapshots.speeding_count IS 'Count of vehicles currently speeding (>60 km/h)';
COMMENT ON COLUMN video_analytics_snapshots.current_in_roi IS 'Count of vehicles currently in ROI';


-- ============================================================================
-- TABLE 2: speeding_vehicles
-- Purpose: Store individual speeding vehicle records for compliance/audit
-- ============================================================================
CREATE TABLE IF NOT EXISTS speeding_vehicles (
    id SERIAL PRIMARY KEY,
    video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    
    -- Vehicle identification
    track_id INTEGER NOT NULL,
    
    -- Speed data
    speed FLOAT NOT NULL,
    speed_unit VARCHAR(10) DEFAULT 'km/h',
    
    -- Vehicle classification
    class_id INTEGER NOT NULL,
    class_name VARCHAR(50),
    confidence FLOAT,
    
    -- Detection metadata
    frame_number INTEGER NOT NULL,
    timestamp FLOAT NOT NULL,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Session tracking
    session_start TIMESTAMP,
    
    CONSTRAINT unique_vehicle_detection UNIQUE (video_id, track_id, frame_number)
);

CREATE INDEX IF NOT EXISTS idx_speeding_vehicles_video_id ON speeding_vehicles(video_id);
CREATE INDEX IF NOT EXISTS idx_speeding_vehicles_track_id ON speeding_vehicles(video_id, track_id);
CREATE INDEX IF NOT EXISTS idx_speeding_vehicles_speed ON speeding_vehicles(speed);
CREATE INDEX IF NOT EXISTS idx_speeding_vehicles_timestamp ON speeding_vehicles(timestamp);
CREATE INDEX IF NOT EXISTS idx_speeding_vehicles_session ON speeding_vehicles(video_id, session_start);

COMMENT ON TABLE speeding_vehicles IS 'Individual speeding vehicle records for compliance and historical analysis';
COMMENT ON COLUMN speeding_vehicles.track_id IS 'DeepSORT tracking ID (unique per video session)';
COMMENT ON COLUMN speeding_vehicles.speed IS 'Detected speed value (>60 km/h threshold)';
COMMENT ON COLUMN speeding_vehicles.class_id IS 'COCO class ID (2=car, 3=motorcycle, 5=bus, 7=truck)';
COMMENT ON COLUMN speeding_vehicles.confidence IS 'YOLOv8 detection confidence (0.0-1.0)';


-- ============================================================================
-- TABLE 3: video_analytics_summary (Optional - for aggregated reports)
-- Purpose: Store final aggregated statistics after video processing completes
-- ============================================================================
CREATE TABLE IF NOT EXISTS video_analytics_summary (
    id SERIAL PRIMARY KEY,
    video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    
    -- Aggregated counts
    total_vehicles_detected INTEGER DEFAULT 0,
    total_speeding_violations INTEGER DEFAULT 0,
    max_concurrent_vehicles INTEGER DEFAULT 0,
    
    -- Performance metrics
    avg_processing_fps FLOAT,
    total_frames_processed INTEGER,
    
    -- Vehicle type distribution
    vehicle_type_distribution JSONB,
    
    -- Speed statistics
    avg_speed FLOAT,
    max_speed FLOAT,
    speed_distribution JSONB,
    
    -- Session metadata
    session_start TIMESTAMP,
    session_end TIMESTAMP,
    processing_duration_seconds INTEGER,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT unique_video_session UNIQUE (video_id, session_start)
);

CREATE INDEX IF NOT EXISTS idx_analytics_summary_video_id ON video_analytics_summary(video_id);
CREATE INDEX IF NOT EXISTS idx_analytics_summary_session ON video_analytics_summary(session_start);

COMMENT ON TABLE video_analytics_summary IS 'Final aggregated analytics after video processing completes';
COMMENT ON COLUMN video_analytics_summary.total_speeding_violations IS 'Count of unique speeding vehicles detected';
COMMENT ON COLUMN video_analytics_summary.vehicle_type_distribution IS 'JSON: {"car": 45, "truck": 12, "bus": 3}';
COMMENT ON COLUMN video_analytics_summary.speed_distribution IS 'JSON: {"60-70": 20, "70-80": 15, "80+": 5}';


-- ============================================================================
-- CLEANUP: Drop old table if exists (backward compatibility)
-- ============================================================================
DROP TABLE IF EXISTS video_analytics CASCADE;