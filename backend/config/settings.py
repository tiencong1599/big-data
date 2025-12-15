import os
from dotenv import load_dotenv

load_dotenv()

# Database configuration
DATABASE_URL = os.getenv(
    'DATABASE_URL', 
    'postgresql://postgres:postgres@localhost:5432/video_streaming'
)

# Redis configuration (replaces Kafka)
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_VIDEO_STREAM = os.getenv('REDIS_VIDEO_STREAM', 'video-frames')
REDIS_RESULT_STREAM = os.getenv('REDIS_RESULT_STREAM', 'processed-frames')

# Legacy Kafka config (kept for backward compatibility)
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
KAFKA_VIDEO_TOPIC = os.getenv('KAFKA_VIDEO_TOPIC', 'video-frames')
KAFKA_RESULT_TOPIC = os.getenv('KAFKA_RESULT_TOPIC', 'processed-frames')

# Video storage configuration
VIDEO_STORAGE_PATH = os.getenv('VIDEO_STORAGE_PATH', '../video_storage')

# Airflow configuration
AIRFLOW_API_URL = os.getenv('AIRFLOW_API_URL', 'http://localhost:8080/api/v1')
AIRFLOW_USERNAME = os.getenv('AIRFLOW_USERNAME', 'admin')
AIRFLOW_PASSWORD = os.getenv('AIRFLOW_PASSWORD', 'admin')

# Server configuration
SERVER_PORT = int(os.getenv('SERVER_PORT', '8686'))
ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', 'http://localhost:4200').split(',')
