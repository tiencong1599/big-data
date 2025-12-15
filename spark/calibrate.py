import cv2
import numpy as np
import glob
import json
import argparse
import tkinter as tk
from tkinter import simpledialog, messagebox

# --- Part 1: Camera Intrinsic Calibration ---

def calibrate_camera(images_folder, chessboard_size=(9, 6), square_size=0.025):
    """
    Performs camera calibration using chessboard images.
    
    This function finds the camera intrinsic matrix (K) and distortion coefficients.
    
    Args:
        images_folder (str): Path to the folder containing chessboard images.
        chessboard_size (tuple): (width, height) of inner corners on the chessboard.
        square_size (float): The real-world size of a chessboard square (e.g., in meters).
    """
    print("Starting camera calibration...")
    
    # termination criteria
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    
    # prepare object points, like (0,0,0), (1,0,0), (2,0,0) ....,(6,5,0)
    objp = np.zeros((chessboard_size[0] * chessboard_size[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:chessboard_size[0], 0:chessboard_size[1]].T.reshape(-1, 2)
    objp = objp * square_size # Scale to real-world size

    # Arrays to store object points and image points from all the images.
    objpoints = [] # 3d point in real world space
    imgpoints = [] # 2d points in image plane.
    
    images = glob.glob(f"{images_folder}/*.jpg")
    if not images:
        print(f"No images found in {images_folder}. Use .jpg format.")
        return

    print(f"Found {len(images)} images.")
    found_count = 0

    for fname in images:
        img = cv2.imread(fname)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Find the chess board corners
        ret, corners = cv2.findChessboardCorners(gray, chessboard_size, None)
        
        # If found, add object points, image points (after refining them)
        if ret == True:
            found_count += 1
            objpoints.append(objp)
            
            corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
            imgpoints.append(corners2)
            
            # Draw and display the corners
            cv2.drawChessboardCorners(img, chessboard_size, corners2, ret)
            cv2.imshow('img', cv2.resize(img, (800, 600)))
            cv2.waitKey(500)
        else:
            print(f"Chessboard not found in {fname}")

    cv2.destroyAllWindows()
    
    if found_count == 0:
        print("Could not find chessboard in any image. Calibration failed.")
        return
    
    print(f"Found chessboard in {found_count}/{len(images)} images.")
    print("Running calibration...")
    
    try:
        ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(objpoints, imgpoints, gray.shape[::-1], None, None)
        
        if ret:
            print("\n--- Calibration Successful ---")
            print("Camera Matrix (K):")
            print(mtx)
            print("\nDistortion Coefficients:")
            print(dist)
            
            # Save results
            calibration_data = {
                'camera_matrix_K': mtx.tolist(),
                'distortion_coefficients': dist.tolist()
            }
            with open('camera_calibration.json', 'w') as f:
                json.dump(calibration_data, f, indent=4)
            print("\nCalibration data saved to 'camera_calibration.json'")
            print("==> config.py will now read this file automatically.")
        else:
            print("\nCalibration failed.")
            
    except cv2.error as e:
        print(f"\nCalibration failed with OpenCV error: {e}")
        print("This can happen if not enough unique chessboard views are provided.")

# --- Part 2: Homography Calculation (Perspective Transform) ---

# Global variables for mouse callback
image_points = []
world_points_input = []
homography_image = None

roi_points = []
roi_image = None

def click_event(event, x, y, flags, params):
    """Mouse callback function to select points for homography."""
    global image_points, homography_image, world_points_input
    
    if event == cv2.EVENT_LBUTTONDOWN:
        if len(image_points) < 4:
            image_points.append((x, y))
            print(f"Selected image point {len(image_points)}: ({x}, {y})")
            
            cv2.circle(homography_image, (x, y), 5, (0, 0, 255), -1)
            cv2.putText(homography_image, str(len(image_points)), (x+5, y+5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            cv2.imshow("Select 4 Points", homography_image)
            
            root = tk.Tk()
            root.withdraw()
            
            while True:
                try:
                    val = simpledialog.askstring(
                        "Input Coordinates",
                        f"Point {len(image_points)} Real-World Coordinates (X,Y):\n(e.g., 5.5, 2.1)"
                    )
                    
                    if val is None:
                        image_points.pop() 
                        print("Point input cancelled.")
                        root.destroy()
                        break
                    
                    x_str, y_str = val.split(',')
                    x_coord = float(x_str.strip())
                    y_coord = float(y_str.strip())
                    world_points_input.append((x_coord, y_coord))
                    print(f"  World point {len(image_points)}: ({x_coord}, {y_coord})")
                    root.destroy()
                    break
                except ValueError:
                    root = tk.Tk()
                    root.withdraw()
                    simpledialog.messagebox.showerror(
                        "Invalid Input",
                        "Please enter in 'X,Y' format (e.g., '5.5, 2.1')"
                    )
            
            if len(image_points) == 4:
                print("\nAll 4 points selected.")
                calculate_homography_matrix()

def click_event_roi(event, x, y, flags, params):
    """Mouse callback function to select points for ROI."""
    global roi_points, roi_image
    
    if event == cv2.EVENT_LBUTTONDOWN:
        # Add the clicked point
        roi_points.append((x, y))
        point_num = len(roi_points)
        print(f"Added ROI point {point_num}: ({x}, {y})")
        
        # Draw on image
        cv2.circle(roi_image, (x, y), 5, (0, 255, 0), -1)
        cv2.putText(roi_image, str(point_num), (x+5, y+5), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # If we have more than one point, draw the polygon line
        if point_num > 1:
            cv2.line(roi_image, roi_points[-2], roi_points[-1], (0, 255, 0), 2)
        
        cv2.imshow("Select ROI Points (Press 's' to save)", roi_image)

def calculate_homography_matrix():
    """Calculates and prints the homography matrix."""
    global image_points, world_points_input
    
    if len(image_points) != 4 or len(world_points_input) != 4:
        print("Error: Need exactly 4 image points and 4 world points.")
        return
        
    print("\nCalculating Homography Matrix (Image -> World)...")
    
    # Convert to numpy arrays
    src_points = np.float32(image_points)
    dst_points = np.float32(world_points_input)
    
    # Calculate Homography (Image to World)
    H, mask = cv2.findHomography(src_points, dst_points)
    
    print("\n--- Homography Calculation Successful ---")
    print("Image-to-World Homography Matrix (H):")
    print(H)
    
    # Save Homography Matrix to JSON
    homography_data = {
        'homography_matrix_H': H.tolist()
    }
    with open('homography_config.json', 'w') as f:
        json.dump(homography_data, f, indent=4)
    
    print("\nHomography data saved to 'homography_config.json'")
    
    print("\n--- Verification (World -> Image) ---")
    # Calculate inverse (World to Image) for verification
    H_inv, _ = cv2.findHomography(dst_points, src_points)
    
    # Test by transforming world points back to image
    for i in range(4):
        world_pt = np.array([world_points_input[i][0], world_points_input[i][1], 1.0])
        img_pt_hom = H_inv @ world_pt
        img_pt = (img_pt_hom[0] / img_pt_hom[2], img_pt_hom[1] / img_pt_hom[2])
        
        print(f"World {world_points_input[i]} -> Image {img_pt} (Original: {image_points[i]})")
        
    print("\n==> config.py will now read this file automatically.")
    cv2.destroyAllWindows()

def save_roi_polygon():
    """Saves the ROI polygon to a JSON file."""
    global roi_points
    
    if len(roi_points) < 3:
        print("Error: Need at least 3 points to define a polygon.")
        return
    
    print(f"\n--- ROI Polygon Saved ---")
    print(f"Number of points: {len(roi_points)}")
    print("Points:")
    for i, pt in enumerate(roi_points):
        print(f"  {i+1}. {pt}")
    
    # Save to JSON
    roi_data = {
        'roi_polygon': roi_points
    }
    with open('roi_config.json', 'w') as f:
        json.dump(roi_data, f, indent=4)
    
    print("\nROI polygon saved to 'roi_config.json'")
    print("==> config.py will now read this file automatically.")

def calculate_homography_interactive(video_path):
    """
    Main function to run the interactive homography calculation.
    
    Args:
        video_path (str): Path to a single frame from your video.
    """
    global homography_image, image_points
    image_points = []

    print("--- Interactive Homography Calculation ---")
    print("1. Click on 4 known points in the image (e.g., corners of a rectangle on the road).")
    print("   Click them in a consistent order (e.g., top-left, top-right, bottom-right, bottom-left).")
    print("2. After 4 points are selected, you will be prompted to enter their")
    print("   corresponding 4 real-world (X, Y) coordinates in the same order.")
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
       print(f"Error: Could not open video file {video_path}")
       return
    
    frame_idx = 0
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx == 0:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            homography_image = frame_rgb.copy()
            
            cv2.namedWindow("Select 4 Points")
            cv2.setMouseCallback("Select 4 Points", click_event)
            cv2.imshow("Select 4 Points", homography_image)
            
            print("\nWaiting for 4 points to be selected... (Press 'q' to quit)")

            # Wait for all 4 points to be selected
            while len(image_points) < 4:
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
            break
        frame_idx += 1
    
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    cap.release()

def select_roi_interactive(video_path):
    """
    Interactive ROI polygon selection.
    
    Args:
        video_path (str): Path to the video file.
    """
    global roi_image, roi_points
    roi_points = []

    print("\n--- Interactive ROI Selection ---")
    print("1. Click on points to define the Region of Interest polygon.")
    print("2. Click points in order (clockwise or counter-clockwise).")
    print("3. Press 's' to save the ROI when done.")
    print("4. Press 'c' to clear all points and start over.")
    print("5. Press 'q' to quit without saving.")
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video file {video_path}")
        return
    
    # Get first frame
    ret, frame = cap.read()
    if not ret:
        print("Error: Could not read frame from video")
        cap.release()
        return
    
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    roi_image = frame_rgb.copy()
    original_image = frame_rgb.copy()
    
    cv2.namedWindow("Select ROI Points (Press 's' to save)")
    cv2.setMouseCallback("Select ROI Points (Press 's' to save)", click_event_roi)
    cv2.imshow("Select ROI Points (Press 's' to save)", roi_image)
    
    print("\nClick to add ROI points...")
    
    while True:
        key = cv2.waitKey(1) & 0xFF
        
        if key == ord('s'):
            if len(roi_points) >= 3:
                # Draw final polygon
                pts = np.array(roi_points, np.int32)
                pts = pts.reshape((-1, 1, 2))
                cv2.polylines(roi_image, [pts], True, (0, 255, 0), 2)
                
                # Draw semi-transparent fill
                overlay = roi_image.copy()
                cv2.fillPoly(overlay, [pts], (0, 255, 0))
                roi_image = cv2.addWeighted(roi_image, 0.7, overlay, 0.3, 0)
                
                cv2.imshow("Select ROI Points (Press 's' to save)", roi_image)
                cv2.waitKey(500)
                
                save_roi_polygon()
                break
            else:
                print("Error: Need at least 3 points to define a polygon. Current points:", len(roi_points))
        
        elif key == ord('c'):
            # Clear all points
            roi_points = []
            roi_image = original_image.copy()
            cv2.imshow("Select ROI Points (Press 's' to save)", roi_image)
            print("Cleared all ROI points.")
        
        elif key == ord('q'):
            print("ROI selection cancelled.")
            break
    
    cv2.destroyAllWindows()
    cap.release()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Camera Calibration and Homography Utility")
    parser.add_argument(
        "--mode",
        type=str,
        required=True,
        choices=['calibrate', 'homography', 'roi'],
        help="Mode to run: 'calibrate' (for camera intrinsics), 'homography' (for perspective transform), or 'roi' (for region of interest)."
    )
    parser.add_argument(
        "--path",
        type=str,
        required=True,
        help="Path to the folder of calibration images (for 'calibrate' mode) or video file (for 'homography'/'roi' mode)."
    )
    
    args = parser.parse_args()
    
    if args.mode == 'calibrate':
        print("Run 'calibrate' mode:")
        print("1. Take 15-20 photos of a chessboard with your camera.")
        print(f"2. Place them in the folder: {args.path}")
        print("3. Press 'Enter' to continue.")
        input()
        calibrate_camera(args.path, chessboard_size=(9, 6))
        
    elif args.mode == 'homography':
        print("Run 'homography' mode:")
        print("1. Take a clear frame from your video showing the road.")
        print(f"2. Save it to: {args.path}")
        print("3. Measure 4 known points on the road (e.g., corners of a parking space)")
        print("   to get their real-world (X, Y) coordinates in meters.")
        print("4. Press 'Enter' to continue.")
        input()
        calculate_homography_interactive(args.path)
    
    elif args.mode == 'roi':
        print("Run 'roi' mode:")
        print("1. Provide a video file showing the area where you want to track vehicles.")
        print(f"2. Video path: {args.path}")
        print("3. Press 'Enter' to continue.")
        input()
        select_roi_interactive(args.path)