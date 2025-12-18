-- backend/migrations/add_analytics_table.sql

CREATE TABLE IF NOT EXISTS video_analytics (
    id SERIAL PRIMARY KEY,
    video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    total_vehicles_count INTEGER DEFAULT 0,
    avg_dwell_time FLOAT DEFAULT 0.0,
    vehicle_type_distribution JSONB,
    processed_at FLOAT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_video_analytics_video_id ON video_analytics(video_id);

-- Comments for documentation
COMMENT ON TABLE video_analytics IS 'Stores aggregated vehicle analytics data per video (dumped from Redis after processing)';
COMMENT ON COLUMN video_analytics.total_vehicles_count IS 'Total number of vehicles that entered the ROI';
COMMENT ON COLUMN video_analytics.avg_dwell_time IS 'Average time (seconds) vehicles spent in ROI';
COMMENT ON COLUMN video_analytics.vehicle_type_distribution IS 'JSON object with vehicle type counts: {"car": 10, "truck": 5, ...}';
COMMENT ON COLUMN video_analytics.processed_at IS 'Unix timestamp when analytics were processed';