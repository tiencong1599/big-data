/**
 * Violation Capture Models
 * TypeScript interfaces for speed violation data
 */

/**
 * Bounding box coordinates for violation vehicle
 */
export interface ViolationBBox {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

/**
 * Single violation capture record
 */
export interface ViolationCapture {
  id: number;
  video_id: number;
  track_id: number;
  
  // Speed data
  speed: number;           // Actual speed in km/h
  speed_limit: number;     // Speed limit threshold
  speed_excess: number;    // Amount over limit
  
  // Vehicle info
  vehicle_type: string;    // car, truck, bus, motorcycle
  class_id: number;        // YOLO class ID
  confidence: number | null;
  
  // Frame data
  frame_number: number;
  frame_image_path: string;
  thumbnail_path: string | null;
  bbox: ViolationBBox;
  
  // Timestamps
  violation_timestamp: string;
  video_timestamp: number | null;
  created_at: string;
  session_start: string | null;
}

/**
 * Vehicle type statistics
 */
export interface VehicleTypeStat {
  vehicle_type: string;
  count: number;
  avg_speed: number;
  max_speed: number;
  min_speed: number;
}

/**
 * Speed distribution by range
 */
export interface SpeedDistribution {
  '60-70': number;
  '70-80': number;
  '80-90': number;
  '90-100': number;
  '100+': number;
  [key: string]: number;
}

/**
 * Overall speed statistics
 */
export interface SpeedStats {
  avg_speed: number;
  max_speed: number;
  min_speed: number;
  avg_excess: number;
}

/**
 * Violation statistics response
 */
export interface ViolationStats {
  total_violations: number;
  recent_violations_24h: number;
  by_vehicle_type: VehicleTypeStat[];
  speed_distribution: SpeedDistribution;
  speed_stats: SpeedStats;
  hourly_distribution: { [hour: string]: number };
}

/**
 * Paginated violations list response
 */
export interface ViolationListResponse {
  violations: ViolationCapture[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

/**
 * Filter options for violation queries
 */
export interface ViolationFilter {
  video_id?: number;
  session_start?: string;
  vehicle_type?: string;
  min_speed?: number;
  max_speed?: number;
  date_from?: string;
  date_to?: string;
}

/**
 * Sort options
 */
export type SortField = 'violation_timestamp' | 'speed' | 'speed_excess' | 'vehicle_type';
export type SortOrder = 'asc' | 'desc';

/**
 * Export format options
 */
export type ExportFormat = 'json' | 'csv';

/**
 * Helper function to get vehicle emoji
 */
export function getVehicleEmoji(vehicleType: string): string {
  const emojiMap: { [key: string]: string } = {
    'car': '🚗',
    'truck': '🚚',
    'bus': '🚌',
    'motorcycle': '🏍️',
    'bicycle': '🚲',
    'unknown': '🚙'
  };
  return emojiMap[vehicleType.toLowerCase()] || '🚙';
}

/**
 * Helper function to get speed severity class
 */
export function getSpeedSeverity(speed: number): 'low' | 'medium' | 'high' | 'extreme' {
  if (speed >= 100) return 'extreme';
  if (speed >= 80) return 'high';
  if (speed >= 70) return 'medium';
  return 'low';
}

/**
 * Helper function to get severity color
 */
export function getSeverityColor(severity: string): string {
  const colorMap: { [key: string]: string } = {
    'low': '#ffc107',      // Yellow
    'medium': '#fd7e14',   // Orange
    'high': '#dc3545',     // Red
    'extreme': '#6f42c1'   // Purple
  };
  return colorMap[severity] || '#dc3545';
}
