# Video Streaming Application

A comprehensive video streaming application built with **Tornado** (backend) and **Angular** (frontend), featuring real-time video frame processing using **Kafka**, **Spark**, and **Airflow**.

## Architecture Overview

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│   Angular   │◄────────┤   Tornado    │◄────────┤  PostgreSQL │
│   Frontend  │ WebSocket│   Backend    │         │  Database   │
└─────────────┘         └──────────────┘         └─────────────┘
                              │  ▲
                              │  │
                    ┌─────────▼──┴────────┐
                    │     Airflow DAG     │
                    │  (Orchestration)    │
                    └─────────┬───────────┘
                              │
                    ┌─────────▼──────────┐
                    │  Kafka Producer    │
                    │ (Video Frames)     │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │      Kafka         │
                    │   (Message Queue)  │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │  Spark Streaming   │
                    │ (Frame Processing) │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │   WebSocket Sender │
                    │   (To Frontend)    │
                    └────────────────────┘
```

## Features

### Video Upload
- Upload videos with metadata (ROI, calibrate coordinates, name)
- Store video files in local storage
- Save video information in PostgreSQL database

### Video Dashboard
- Display all uploaded videos in a grid layout
- Click to select and view video details
- Split-view interface (dashboard + detail panel)

### Video Streaming
- Stream video frames through Kafka and Spark pipeline
- Real-time frame processing and display
- WebSocket-based communication for low latency
- Airflow DAG orchestration

## Project Structure

```
BDataFinalProject/
├── backend/                    # Tornado backend
│   ├── config/
│   │   └── settings.py         # Configuration settings
│   ├── handlers/
│   │   ├── video_handler.py    # Video upload/list/detail APIs
│   │   └── stream_handler.py   # Streaming and WebSocket handlers
│   ├── models/
│   │   └── video.py            # Database models
│   ├── services/
│   │   ├── kafka_producer.py   # Kafka producer for frames
│   │   └── kafka_consumer.py   # Kafka consumer for results
│   ├── app.py                  # Main application entry
│   ├── requirements.txt        # Python dependencies
│   └── .env.example            # Environment variables template
│
├── frontend/                   # Angular frontend
│   ├── src/
│   │   ├── app/
│   │   │   ├── components/
│   │   │   │   ├── dashboard.component.*      # Main dashboard
│   │   │   │   ├── video-detail.component.*   # Video detail panel
│   │   │   │   └── video-upload.component.*   # Upload form
│   │   │   ├── services/
│   │   │   │   ├── video.service.ts           # Video API service
│   │   │   │   └── websocket.service.ts       # WebSocket service
│   │   │   ├── models/
│   │   │   │   └── video.model.ts             # TypeScript interfaces
│   │   │   ├── app.module.ts
│   │   │   └── app.component.ts
│   │   ├── index.html
│   │   ├── main.ts
│   │   └── styles.css
│   ├── angular.json
│   ├── package.json
│   └── tsconfig.json
│
├── airflow/                    # Airflow DAGs
│   ├── dags/
│   │   └── video_streaming_dag.py  # Video streaming pipeline
│   └── requirements.txt
│
├── spark/                      # Spark processing
│   └── video_frame_processor.py    # Frame processor
│
└── video_storage/              # Video file storage
```

## Prerequisites

### Option 1: Docker (Recommended)
- **Docker Desktop** (includes Docker Compose)
- At least 8GB RAM allocated to Docker
- 20GB free disk space

### Option 2: Manual Installation
- **Python 3.8+**
- **Node.js 18+** and npm
- **PostgreSQL 12+**
- **Apache Kafka 3.0+**
- **Apache Spark 3.5+**
- **Apache Airflow 2.8+**

## Installation & Setup

### 🐳 Docker Deployment (Recommended)

The easiest way to run the entire application is using Docker:

#### Quick Start with Docker

```bash
# 1. Start all services
docker-setup.bat

# Or manually:
docker-compose up -d

# 2. Wait 2-3 minutes for all services to start

# 3. Access the application
# Frontend: http://localhost:4200
# Backend:  http://localhost:8888
# Airflow:  http://localhost:8080 (admin/admin)

# 4. View logs
docker-compose logs -f

# 5. Stop services
docker-compose down
```

#### Docker Management Scripts

- **docker-setup.bat** - Complete setup (build + start)
- **docker-start.bat** - Start all services
- **docker-stop.bat** - Stop all services
- **docker-logs.bat** - View service logs
- **docker-status.bat** - Check service status

For detailed Docker instructions, see [DOCKER_GUIDE.md](DOCKER_GUIDE.md)

### 📦 Manual Installation & Setup

### 1. Database Setup

```bash
# Create PostgreSQL database
createdb video_streaming

# Or using psql
psql -U postgres
CREATE DATABASE video_streaming;
```

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file
copy .env.example .env

# Edit .env file with your configuration
# Update DATABASE_URL, KAFKA_BOOTSTRAP_SERVERS, etc.

# Run backend server
python app.py
```

The backend will start on `http://localhost:8888`

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm start
```

The frontend will start on `http://localhost:4200`

### 4. Kafka Setup

```bash
# Start Zookeeper
zookeeper-server-start.bat config\zookeeper.properties

# Start Kafka server (in new terminal)
kafka-server-start.bat config\server.properties

# Create topics
kafka-topics.bat --create --topic video-frames --bootstrap-server localhost:9092 --partitions 3 --replication-factor 1
kafka-topics.bat --create --topic processed-frames --bootstrap-server localhost:9092 --partitions 3 --replication-factor 1
```

### 5. Spark Setup

```bash
cd spark

# Submit Spark job
spark-submit --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0 video_frame_processor.py
```

### 6. Airflow Setup

```bash
cd airflow

# Initialize Airflow database
airflow db init

# Create admin user
airflow users create --username admin --password admin --firstname Admin --lastname User --role Admin --email admin@example.com

# Start Airflow webserver (in one terminal)
airflow webserver --port 8080

# Start Airflow scheduler (in another terminal)
airflow scheduler

# Copy DAG file to Airflow dags folder
# Update AIRFLOW_HOME/dags/ with video_streaming_dag.py
```

Access Airflow UI at `http://localhost:8080`

### 7. Start Kafka Consumer (Backend Service)

```bash
cd backend

# In a new terminal with activated venv
python services/kafka_consumer.py
```

## Usage

### Upload a Video

1. Open the Angular frontend at `http://localhost:4200`
2. Click **"+ Upload Video"** button
3. Fill in the form:
   - Select a video file
   - Enter video name
   - (Optional) Add ROI as JSON: `{"x": 100, "y": 100, "width": 500, "height": 300}`
   - (Optional) Add calibrate coordinates as JSON: `{"points": [[0,0], [100,100]]}`
4. Click **"Upload"**

### Stream a Video

1. Click on any video card in the dashboard
2. The video detail panel will appear on the right side
3. View video information (name, ROI, calibrate coordinates)
4. Click **"Start Stream"** button
5. The system will:
   - Trigger Airflow DAG
   - Producer reads video frames
   - Sends frames to Kafka
   - Spark processes frames
   - Results sent to frontend via WebSocket
6. Video frames appear in real-time in the display area
7. Click **"Stop Stream"** to end streaming

## API Endpoints

### Video APIs

```
POST   /api/videos/upload     - Upload video with metadata
GET    /api/videos            - Get all videos
GET    /api/videos/:id        - Get video details
```

### Streaming APIs

```
POST   /api/stream/start      - Start video streaming
WS     /ws/stream?video_id=X  - WebSocket connection for frames
```

## Configuration

### Backend (.env)

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/video_streaming
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_VIDEO_TOPIC=video-frames
KAFKA_RESULT_TOPIC=processed-frames
VIDEO_STORAGE_PATH=../video_storage
AIRFLOW_API_URL=http://localhost:8080/api/v1
AIRFLOW_USERNAME=admin
AIRFLOW_PASSWORD=admin
SERVER_PORT=8888
ALLOWED_ORIGINS=http://localhost:4200
```

## Technologies Used

### Backend
- **Tornado** - Asynchronous web framework
- **SQLAlchemy** - ORM for database operations
- **PostgreSQL** - Relational database
- **Kafka-Python** - Kafka client
- **OpenCV** - Video processing

### Data Processing
- **Apache Kafka** - Message broker
- **Apache Spark** - Stream processing
- **Apache Airflow** - Workflow orchestration

### Frontend
- **Angular 17** - Frontend framework
- **TypeScript** - Type-safe JavaScript
- **RxJS** - Reactive programming
- **WebSocket** - Real-time communication

## Troubleshooting

### Backend Issues
- Ensure PostgreSQL is running and database exists
- Check `.env` file configuration
- Verify all Python dependencies are installed

### Kafka Issues
- Ensure Zookeeper and Kafka server are running
- Verify topics are created
- Check Kafka broker connectivity

### Airflow Issues
- Ensure Airflow database is initialized
- Check DAG file is in correct dags folder
- Verify Airflow webserver and scheduler are running

### WebSocket Issues
- Check backend WebSocket handler is running
- Verify CORS settings allow frontend origin
- Ensure Kafka consumer service is running

## Future Enhancements

- Add video preview/thumbnails
- Implement video analytics (object detection, tracking)
- Add user authentication and authorization
- Support multiple video formats
- Add video playback controls (pause, seek)
- Implement video transcoding
- Add real-time notifications
- Support distributed deployment

## License

MIT License

## Contributors

Your Name - Initial work
