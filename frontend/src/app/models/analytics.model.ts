export interface AnalyticsSummary {
  id: number;
  video_id: number;
  session_start: string;
  session_end: string;
  total_vehicles_detected: number;
  total_speeding_violations: number;
  max_concurrent_vehicles: number;
  avg_fps: number;
  speed_distribution: {
    range_60_70: number;
    range_70_80: number;
    range_80_90: number;
    range_90_plus: number;
  };
  vehicle_type_distribution: {
    [type: string]: number;
  };
}

export interface AnalyticsSnapshot {
  id: number;
  video_id: number;
  session_start: string;
  timestamp: string;
  total_vehicles: number;
  speeding_count: number;
  current_in_roi: number;
  max_speed: number;
}

export interface SpeedingVehicleRecord {
  id: number;
  video_id: number;
  session_start: string;
  track_id: number;
  speed: number;
  class_id: number;
  timestamp: string;
  confidence: number;
}

export interface AnalyticsSession {
  session_start: string;
  session_end: string;
  total_vehicles: number;
  speeding_violations: number;
}

export interface AnalyticsTrend {
  timestamp: string;
  avg_total: number;
  avg_speeding: number;
  max_speed: number;
}

export interface AnalyticsAggregateResponse {
  summary?: AnalyticsSummary[];
  snapshots?: AnalyticsSnapshot[];
  speeding?: SpeedingVehicleRecord[];
  trends?: AnalyticsTrend[];
}
