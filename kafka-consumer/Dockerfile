FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements from backend (consumer needs same dependencies)
COPY backend/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code (consumer imports from backend modules)
COPY backend /app

# Run Redis consumer with unbuffered output
CMD ["python", "-u", "-m", "services.redis_consumer"]
