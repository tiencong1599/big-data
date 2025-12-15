import cv2
import numpy as np
import config
import random

# Generate a cache of random colors for track IDs
COLOR_CACHE = {}

def get_color(track_id):
    """
    Generates a consistent random color for a given track ID.
    """
    if track_id not in COLOR_CACHE:
        random.seed(track_id)
        COLOR_CACHE[track_id] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
    return COLOR_CACHE[track_id]

def draw_results(frame, tracks, speeds):
    """
    Draws bounding boxes, track IDs, and speed information on the frame.
    
    Args:
        frame (np.ndarray): The video frame to draw on (BGR).
        tracks (list): List of active tracks. Each: (track_id, [x1, y1, x2, y2])
        speeds (dict): Dictionary mapping {track_id: speed}
        
    Returns:
        np.ndarray: The frame with annotations.
    """
    annotated_frame = frame.copy()
    
    for track_id, bbox in tracks:
        x1, y1, x2, y2 = bbox
        color = get_color(track_id)
        
        # Draw bounding box
        cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)
        
        # Prepare text
        speed = speeds.get(track_id, 0.0)
        label = f"ID: {track_id} | {speed:.1f} {config.SPEED_UNIT}"
        
        # Calculate text size
        (text_w, text_h), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        
        # Draw text background
        cv2.rectangle(annotated_frame, (x1, y1 - text_h - 10), (x1 + text_w, y1), color, -1)
        
        # Draw text
        cv2.putText(
            annotated_frame,
            label,
            (x1, y1 - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255), # White text
            2
        )
        
    return annotated_frame

def draw_perspective_grid(frame, homography_matrix, grid_size=1.0, world_range=((-10, 10), (-2, 20))):
    """
    Draws a grid on the ground plane to visualize the 3D perspective.
    
    Args:
        frame (np.ndarray): The frame to draw on.
        homography_matrix (np.ndarray): The H matrix (world-to-image).
        grid_size (float): Spacing of the grid lines in world units (e.g., 1 meter).
        world_range (tuple): ((min_x, max_x), (min_y, max_y)) in world units.
    """
    # We need the inverse (world-to-image) to draw
    try:
        H_inv = np.linalg.inv(homography_matrix)
    except np.linalg.LinAlgError:
        print("Error: Homography matrix is singular, cannot draw grid.")
        return frame

    h, w = frame.shape[:2]
    (min_x, max_x), (min_y, max_y) = world_range
    
    # Generate grid lines in world coordinates
    lines_world = []
    
    # Lines along X-axis
    for y in np.arange(min_y, max_y + grid_size, grid_size):
        lines_world.append(((min_x, y), (max_x, y)))
        
    # Lines along Y-axis
    for x in np.arange(min_x, max_x + grid_size, grid_size):
        lines_world.append(((x, min_y), (x, max_y)))

    # Transform lines to image coordinates and draw
    overlay = frame.copy()
    for p1_world, p2_world in lines_world:
        p1_hom = np.array([p1_world[0], p1_world[1], 1.0])
        p2_hom = np.array([p2_world[0], p2_world[1], 1.0])
        
        p1_img_hom = H_inv @ p1_hom
        p2_img_hom = H_inv @ p2_hom
        
        if p1_img_hom[2] == 0 or p2_img_hom[2] == 0:
            continue
            
        p1_img = (int(p1_img_hom[0] / p1_img_hom[2]), int(p1_img_hom[1] / p1_img_hom[2]))
        p2_img = (int(p2_img_hom[0] / p2_img_hom[2]), int(p2_img_hom[1] / p2_img_hom[2]))
        
        # Draw line
        cv2.line(overlay, p1_img, p2_img, (0, 255, 0), 1, cv2.LINE_AA)
        
    return cv2.addWeighted(frame, 0.7, overlay, 0.3, 0)