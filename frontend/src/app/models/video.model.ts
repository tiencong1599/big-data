export interface Video {
  id: number;
  name: string;
  file_path: string;
  roi: RoiPolygon | null;
  calibrate_coordinates: any;
  homography_matrix: number[][] | null;
  camera_matrix: number[][] | null;
  fps: number;
  created_at: string;
  updated_at: string;
}

export interface RoiPolygon {
  roi_polygon: number[][];
}

export interface VehicleBBox {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface VehicleData {
  track_id: number;
  bbox: VehicleBBox;
  speed: number;
  speed_unit: string;
  confidence: number;
  class_id: number;
}

export interface ProcessedFrameData {
  video_id: number;
  frame_number: number;
  timestamp: number;
  vehicles: VehicleData[];
  roi_polygon: number[][] | null;
  total_vehicles: number;
  error?: string;
  end_of_stream?: boolean;
  message?: string;
  // Full CSR: No 'processed_frame' field (removed Base64)
}

export interface FrameData {
  video_id: string;
  frame_number: number;
  frame_data: string;
  timestamp: number;
}
