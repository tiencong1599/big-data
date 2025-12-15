from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col, udf, to_json
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, LongType, FloatType, ArrayType, MapType
import json
import base64
import cv2
import numpy as np
import os
from detector import VehicleDetector
from tracker import VehicleTracker
from speed_estimator import SpeedEstimator
import visualizer
import config


# Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_INPUT_TOPIC = os.getenv("KAFKA_INPUT_TOPIC", "video-frames")
KAFKA_OUTPUT_TOPIC = os.getenv("KAFKA_OUTPUT_TOPIC", "processed-frames")
ENABLE_VEHICLE_DETECTION = os.getenv("ENABLE_VEHICLE_DETECTION", "true").lower() == "true"

# Global model instances (per executor)
detector = None
tracker = None
# Speed estimator is created per video based on its homography matrix
speed_estimators = {}

def initialize_models():
    """Initialize vehicle detection models once per executor"""
    global detector, tracker
    
    if not ENABLE_VEHICLE_DETECTION:
        return
    
    try:
        if detector is None:
            print("Initializing VehicleDetector...")
            detector = VehicleDetector()
        
        if tracker is None:
            print("Initializing VehicleTracker...")
            tracker = VehicleTracker()
        
        print("Models initialized successfully")
    except Exception as e:
        print(f"Error initializing models: {e}")
        raise

def point_in_polygon(point, polygon):
    """Check if point is inside polygon using ray casting algorithm"""
    if polygon is None or len(polygon) == 0:
        return True
    
    x, y = point
    n = len(polygon)
    inside = False
    
    p1x, p1y = polygon[0]
    for i in range(1, n + 1):
        p2x, p2y = polygon[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    
    return inside

def filter_detections_by_roi(detections, roi_polygon):
    """Filter detections by ROI polygon from database"""
    if roi_polygon is None or len(roi_polygon) == 0:
        return detections
    
    filtered = []
    for detection in detections:
        bbox, conf, class_id = detection
        x1, y1, x2, y2 = bbox
        
        # Use bottom-center of bbox
        center_x = (x1 + x2) / 2
        center_y = y2
        
        if point_in_polygon((center_x, center_y), roi_polygon):
            filtered.append(detection)
    
    return filtered

def get_speed_estimator(video_id, homography_matrix, fps):
    """Get or create speed estimator for specific video"""
    global speed_estimators
    
    if video_id not in speed_estimators and homography_matrix:
        H = np.array(homography_matrix, dtype=np.float32)
        speed_estimators[video_id] = SpeedEstimator(homography_matrix=H, fps=fps)
        print(f"Created SpeedEstimator for video {video_id}")
    
    return speed_estimators.get(video_id)

def decode_base64_frame(frame_data):
    """Decode base64-encoded frame data to OpenCV image"""
    frame_bytes = base64.b64decode(frame_data)
    frame_array = np.frombuffer(frame_bytes, dtype=np.uint8)
    frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
    return frame

def encode_to_base64(image):
    """Encode OpenCV image to base64 string with compression"""
    # CRITICAL CHANGE: Use lower quality for faster transmission
    _, buffer = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 60])  # Reduced from 85
    return base64.b64encode(buffer).decode('utf-8')

def process_frame(frame_data, video_id, frame_number, config_json):
    """
    Process video frame with vehicle detection, tracking, and speed estimation
    Configuration is loaded from database (passed via config_json)
    Returns JSON string with processing results
    """
    try:
        # Initialize models if needed
        initialize_models()
        
        # Decode frame
        frame = decode_base64_frame(frame_data)
        
        # Parse configuration from database (sent via Kafka)
        config_data = json.loads(config_json) if config_json else {}
        roi_polygon = config_data.get('roi_polygon')
        homography_matrix = config_data.get('homography_matrix')
        camera_matrix = config_data.get('camera_matrix')
        fps = config_data.get('fps', config.DEFAULT_VIDEO_FPS)
        
        print(f"Processing frame {frame_number} for video {video_id}")
        print(f"  Config: ROI={roi_polygon is not None}, H={homography_matrix is not None}, FPS={fps}")
        
        # If detection disabled, return original frame
        if not ENABLE_VEHICLE_DETECTION or detector is None:
            processed_frame_base64 = encode_to_base64(frame)
            return json.dumps({
                'frame_data': processed_frame_base64,
                'vehicles': [],
                'roi_polygon': roi_polygon,
                'total_vehicles': 0,
                'frame_number': frame_number,
                'video_id': video_id
            })
        
        # Convert to RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # 1. Detection
        detections = detector.detect(frame_rgb)
        
        # 2. Filter by ROI from database
        detections = filter_detections_by_roi(detections, roi_polygon)
        
        # 3. Tracking
        tracks = tracker.update(frame_rgb, detections)
        
        # 4. Speed Estimation using homography from database
        speeds = {}
        estimator = get_speed_estimator(video_id, homography_matrix, fps)
        if estimator:
            speeds = estimator.update(tracks, frame_number)
        
        # 5. Prepare vehicle data
        vehicles = []
        for track_id, bbox in tracks:
            x1, y1, x2, y2 = bbox
            speed = speeds.get(track_id, 0.0)
            
            vehicles.append({
                'track_id': int(track_id),
                'bbox': {
                    'x1': int(x1),
                    'y1': int(y1),
                    'x2': int(x2),
                    'y2': int(y2)
                },
                'speed': float(speed),
                'speed_unit': config.SPEED_UNIT
            })
        
        # 6. Visualization
        annotated_frame = visualizer.draw_results(frame, tracks, speeds)
        
        # Draw ROI polygon from database
        if roi_polygon and len(roi_polygon) > 0:
            pts = np.array(roi_polygon, np.int32)
            pts = pts.reshape((-1, 1, 2))
            cv2.polylines(annotated_frame, [pts], True, (0, 255, 255), 2)
            
            # Add ROI label
            cv2.putText(
                annotated_frame,
                "ROI",
                (pts[0][0][0], pts[0][0][1] - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 255),
                2
            )
        
        # Add info text
        cv2.putText(
            annotated_frame,
            f"Video {video_id} | Frame: {frame_number} | Vehicles: {len(tracks)}",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2
        )
        
        # Encode processed frame
        processed_frame_base64 = encode_to_base64(annotated_frame)
        
        # Return results as JSON
        result = {
            'frame_data': processed_frame_base64,
            'vehicles': vehicles,
            'roi_polygon': roi_polygon,
            'total_vehicles': len(tracks),
            'frame_number': frame_number,
            'video_id': video_id,
            'has_homography': homography_matrix is not None,
            'has_camera_matrix': camera_matrix is not None
        }
        
        return json.dumps(result)
        
    except Exception as e:
        print(f"Error processing frame {frame_number}: {e}")
        import traceback
        traceback.print_exc()
        return json.dumps({
            'error': str(e),
            'frame_number': frame_number,
            'video_id': video_id
        })

def create_spark_session():
    """Create Spark session with Kafka support"""
    return SparkSession.builder \
        .appName("VideoFrameProcessor") \
        .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0") \
        .config("spark.streaming.kafka.maxRatePerPartition", "100") \
        .config("spark.executor.memory", "4g") \
        .config("spark.driver.memory", "2g") \
        .getOrCreate()

def main():
    spark = create_spark_session()
    spark.sparkContext.setLogLevel("WARN")
    
    # Define input schema
    schema = StructType([
        StructField("video_id", IntegerType(), True),
        StructField("frame_number", IntegerType(), True),
        StructField("frame_data", StringType(), True),
        StructField("timestamp", LongType(), True),
        StructField("config", StructType([
            StructField("video_id", IntegerType(), True),
            StructField("roi_polygon", ArrayType(ArrayType(IntegerType())), True),
            StructField("homography_matrix", ArrayType(ArrayType(FloatType())), True),
            StructField("camera_matrix", ArrayType(ArrayType(FloatType())), True),
            StructField("fps", FloatType(), True)
        ]), True),
        StructField("end_of_stream", StringType(), True)
    ])
    
    # Read from Kafka
    df = spark \
        .readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS) \
        .option("subscribe", KAFKA_INPUT_TOPIC) \
        .option("startingOffsets", "latest") \
        .load()
    
    # Parse JSON
    parsed_df = df.selectExpr("CAST(value AS STRING)") \
        .select(from_json(col("value"), schema).alias("data")) \
        .select("data.*")
    
    # Process frames
    process_frame_udf = udf(process_frame, StringType())
    
    # Convert config to JSON string for UDF
    processed_df = parsed_df.withColumn(
        "config_json",
        to_json(col("config"))
    ).withColumn(
        "processing_result",
        process_frame_udf(
            col("frame_data"),
            col("video_id"),
            col("frame_number"),
            col("config_json")
        )
    )
    
    # Parse processing result
    result_schema = StructType([
        StructField("frame_data", StringType(), True),
        StructField("vehicles", ArrayType(
            StructType([
                StructField("track_id", IntegerType(), True),
                StructField("bbox", MapType(StringType(), IntegerType()), True),
                StructField("speed", FloatType(), True),
                StructField("speed_unit", StringType(), True)
            ])
        ), True),
        StructField("roi_polygon", ArrayType(ArrayType(IntegerType())), True),
        StructField("total_vehicles", IntegerType(), True),
        StructField("frame_number", IntegerType(), True),
        StructField("video_id", IntegerType(), True),
        StructField("has_homography", StringType(), True),
        StructField("has_camera_matrix", StringType(), True),
        StructField("error", StringType(), True)
    ])
    
    output_df = processed_df.withColumn(
        "result",
        from_json(col("processing_result"), result_schema)
    ).select(
        col("video_id"),
        col("frame_number"),
        col("timestamp"),
        col("end_of_stream"),
        col("result.frame_data").alias("processed_frame"),
        col("result.vehicles").alias("vehicles"),
        col("result.roi_polygon").alias("roi_polygon"),
        col("result.total_vehicles").alias("total_vehicles"),
        col("result.has_homography").alias("has_homography"),
        col("result.has_camera_matrix").alias("has_camera_matrix"),
        col("result.error").alias("error")
    )
    
    # Write to output Kafka topic
    kafka_query = output_df.selectExpr(
        "CAST(video_id AS STRING) as key",
        "to_json(struct(*)) AS value"
    ).writeStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS) \
        .option("topic", KAFKA_OUTPUT_TOPIC) \
        .option("checkpointLocation", "/tmp/kafka-checkpoint") \
        .trigger(processingTime='100 milliseconds') \
        .start()
    
    kafka_query.awaitTermination()

if __name__ == "__main__":
    main()
