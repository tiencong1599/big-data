from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.utils.dates import days_ago
from datetime import timedelta

dag = DAG(
    'video_streaming_pipeline',
    schedule_interval=None,
    catchup=False
)

# Task 1: Kafka Producer (Ingestion)
# Note: Spark processor and Kafka consumer run as standalone Docker services.
# They continuously process frames in the background.
# This DAG only triggers the producer via backend API.
def start_kafka_producer(**context):
    """Trigger video streaming by calling backend API"""
    import requests
    import json
    
    video_id = context['dag_run'].conf['video_id']
    video_path = context['dag_run'].conf['video_path']
    fps = context['dag_run'].conf.get('fps', 30)
    duration = context['dag_run'].conf.get('duration', 0)
    
    # Call backend API to start producer
    backend_url = 'http://video_streaming_backend:8686/api/producer/stream'
    payload = {
        'video_id': video_id,
        'video_path': video_path,
        'fps': fps,
        'duration': duration
    }
    
    print(f"Calling backend API: {backend_url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    response = requests.post(backend_url, json=payload, timeout=300)
    
    if response.status_code == 200:
        result = response.json()
        print(f"✓ Producer started successfully: {result}")
        return result
    else:
        error_msg = f"Producer API failed with status {response.status_code}: {response.text}"
        print(f"✗ {error_msg}")
        raise Exception(error_msg)

task_producer = PythonOperator(
    task_id='kafka_producer',
    python_callable=start_kafka_producer,
    dag=dag
)

# Only producer task - Spark and Consumer are standalone services
# Data Flow: DAG → Backend Producer → Kafka → Spark (standalone) → Consumer (standalone) → WebSocket
