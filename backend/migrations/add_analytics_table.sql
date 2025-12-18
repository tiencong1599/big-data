-- backend/migrations/add_analytics_table.sql

CREATE TABLE IF NOT EXISTS video_analytics (
    id SERIAL PRIMARY KEY,
    video_id INTEGER NOT NULL REFERENCES video(id) ON DELETE CASCADE,
    total_vehicles_count INTEGER DEFAULT 0,
    avg_dwell_time FLOAT DEFAULT 0.0,
    vehicle_type_distribution JSONB,
    processed_at FLOAT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_video_analytics_video_id ON video_analytics(video_id);