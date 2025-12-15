from deep_sort_realtime.deepsort_tracker import DeepSort

class VehicleTracker:
    """
    Handles vehicle tracking using the DeepSORT algorithm.
    
    This class fuses semantic detections (from YOLO) with visual features
    to maintain a consistent track ID for each vehicle.
    """
    def __init__(self, max_age=30, n_init=3, nms_max_overlap=1.0):
        """
        Initializes the DeepSORT tracker.
        
        Args:
            max_age (int): Maximum number of missed frames before a track is deleted.
            n_init (int): Number of consecutive detections needed to start a track.
            nms_max_overlap (float): NMS overlap threshold.
        """
        self.tracker = DeepSort(
            max_age=max_age,
            n_init=n_init,
            nms_max_overlap=nms_max_overlap,
            max_cosine_distance=0.3,
            nn_budget=None,  # Use default
            override_track_class=None, # Use default
            embedder="mobilenet", # Lightweight and effective
            half=True, # Use half-precision for faster inference
            bgr=False, # Input frames are expected in RGB
            embedder_gpu=True, # Use GPU for embedding (set to False if causing issues)
            embedder_model_name=None, # Use default
            embedder_wts=None, # Use default
            polygon=False, # Not using polygon zones
            today=None # Use default
        )
        print("DeepSORT tracker initialized with optimizations.")

    def update(self, frame, detections):
        """
        Updates the tracker with new detections for the current frame.
        
        Args:
            frame (np.ndarray): The current video frame (RGB).
            detections (list): A list of detections from the VehicleDetector.
                               Each item: ([x1, y1, x2, y2], confidence, class_id)
                               
        Returns:
            list: A list of active tracks. Each track is a tuple:
                  (track_id, [x1, y1, x2, y2])
        """
        # DeepSORT expects detections in a specific format:
        # [( [x1, y1, w, h], confidence, class_id ), ... ]
        deepsort_detections = []
        for det in detections:
            # det format: ([x1, y1, x2, y2], confidence, class_id)
            bbox, conf, class_id = det
            x1, y1, x2, y2 = bbox
            w = x2 - x1
            h = y2 - y1
            deepsort_detections.append(([x1, y1, w, h], conf, str(class_id)))

        # Update the tracker (pass empty list if no detections)
        # The frame is used to extract appearance features (visual fusion)
        tracks = self.tracker.update_tracks(deepsort_detections, frame=frame)
        
        active_tracks = []
        for track in tracks:
            if not track.is_confirmed() or track.time_since_update > 0:
                continue
                
            track_id = track.track_id
            ltrb = track.to_ltrb() # Get box in [x1, y1, x2, y2] format
            active_tracks.append((track_id, list(map(int, ltrb))))
            
        return active_tracks