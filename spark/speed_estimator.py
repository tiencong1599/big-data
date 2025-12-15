import numpy as np
import cv2
import config
from collections import defaultdict

class SpeedEstimator:
    """
    Estimates the 3D speed of tracked vehicles.
    
    This class maps 2D image coordinates to 3D world coordinates using a
    homography matrix and calculates speed based on displacement over time.
    """
    def __init__(self, homography_matrix, fps=config.VIDEO_FPS):
        """
        Initializes the speed estimator.
        
        Args:
            homography_matrix (np.ndarray): The 3x3 homography matrix
                                            mapping image points to world points.
            fps (float): The frames-per-second of the video.
        """
        self.H = homography_matrix
        self.H_inv = np.linalg.inv(homography_matrix)
        self.fps = fps
        self.time_per_frame = 1.0 / fps
        
        # State-keeping dictionaries
        # self.prev_positions = {track_id: (world_x, world_y, frame_number)}
        self.prev_positions = {}
        # self.current_speeds = {track_id: speed_in_kph}
        self.current_speeds = defaultdict(lambda: 0.0)
        
        print(f"SpeedEstimator initialized with FPS: {fps}")

    def _transform_to_world(self, image_point):
        """
        Transforms a 2D image point to 3D world coordinates (on the ground plane).
        
        Args:
            image_point (tuple): (x, y) pixel coordinate.
            
        Returns:
            tuple: (world_x, world_y) coordinate in real-world units (e.g., meters).
        """
        # Create a homogeneous coordinate
        image_point_homogeneous = np.array([image_point[0], image_point[1], 1.0])
        
        # Apply the homography
        world_point_homogeneous = self.H @ image_point_homogeneous
        
        # Normalize to get 2D world coordinates
        if world_point_homogeneous[2] != 0:
            world_x = world_point_homogeneous[0] / world_point_homogeneous[2]
            world_y = world_point_homogeneous[1] / world_point_homogeneous[2]
            return (world_x, world_y)
        else:
            return (None, None)

    def _get_ground_point(self, bbox):
        """
        Gets the 2D point on the image that corresponds to the
        vehicle's position on the ground (bottom-center of the bounding box).
        
        Args:
            bbox (list): [x1, y1, x2, y2]
            
        Returns:
            tuple: (x, y) pixel coordinate.
        """
        x1, y1, x2, y2 = bbox
        ground_x = int((x1 + x2) / 2)
        ground_y = int(y2)
        return (ground_x, ground_y)

    def update(self, tracks, frame_number):
        """
        Updates the speed estimates for all active tracks.
        
        Args:
            tracks (list): List of active tracks from VehicleTracker.
                           Each track: (track_id, [x1, y1, x2, y2])
            frame_number (int): The current frame number.
                           
        Returns:
            dict: A dictionary mapping {track_id: speed_in_configured_unit}
        """
        new_prev_positions = {}
        
        for track_id, bbox in tracks:
            # 1. Get 2D ground point
            img_point = self._get_ground_point(bbox)
            
            # 2. Transform to 3D world point
            world_x, world_y = self._transform_to_world(img_point)
            
            if world_x is None or world_y is None:
                # If transformation fails, skip this track
                continue
                
            # 3. Check if we have a previous position for this track
            if track_id in self.prev_positions:
                prev_x, prev_y, prev_frame = self.prev_positions[track_id]
                
                # 4. Calculate displacement and time elapsed
                delta_frames = frame_number - prev_frame
                if delta_frames > 0:
                    delta_time = delta_frames * self.time_per_frame
                    
                    # Calculate Euclidean distance in the real world (e.g., in meters)
                    distance = np.sqrt((world_x - prev_x)**2 + (world_y - prev_y)**2)
                    
                    # 5. Calculate speed in m/s
                    speed_ms = distance / delta_time
                    
                    # 6. Convert to desired unit (e.g., km/h or mph)
                    speed_converted = speed_ms * config.SPEED_CONVERSION_FACTOR
                    
                    # Use a simple moving average (EMA) to smooth the speed
                    alpha = 0.2 # Smoothing factor
                    current_speed = self.current_speeds[track_id]
                    smoothed_speed = (alpha * speed_converted) + ((1 - alpha) * current_speed)
                    
                    self.current_speeds[track_id] = smoothed_speed
            
            # 7. Store the current position for the next frame
            # We update this regardless of speed calculation to get a
            # more stable (less noisy) displacement vector next time.
            new_prev_positions[track_id] = (world_x, world_y, frame_number)
            
        # Update the state with only the tracks that are still active
        self.prev_positions = new_prev_positions
        
        # Clean up speeds for tracks that have disappeared
        active_track_ids = set(new_prev_positions.keys())
        current_speed_ids = set(self.current_speeds.keys())
        for old_id in (current_speed_ids - active_track_ids):
            del self.current_speeds[old_id]
            
        return self.current_speeds