# Image Translation Backend - Run Guide

Complete guide for running and testing the long polling image translation service.

## Quick Start

### Prerequisites
- Docker and Docker Compose
- Redis (for local development)
- API keys configured in `config/api_keys.json`

### Local Development
```bash
# Install dependencies
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync

# Start Redis
docker run -d -p 6379:6379 --name redis redis:8-alpine

# Run development server
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Alternative: Direct Python
uv run python app/main.py
```

### Docker Development
```bash
# Start all services
docker compose -f docker/docker-compose.yml up -d

# View logs
docker compose -f docker/docker-compose.yml logs -f app

# Rebuild after changes
docker compose -f docker/docker-compose.yml up --build -d
```

### Production Deployment
```bash
# Build production image
docker build -f docker/Dockerfile.prod -t image-translate-backend:prod .

# Run production services (uncomment prod services in docker-compose.yml first)
docker compose -f docker/docker-compose.yml up -d nginx app_prod redis
```

## Configuration Setup

### 1. API Keys (`config/api_keys.json`)
```json
{
  "keys": [
    {
      "id": "key_1",
      "api_key": "your_gemini_api_key_here",
      "limits": {
        "requests_per_minute": 60,
        "requests_per_day": 1440,
        "tokens_per_minute": 32000
      }
    }
  ]
}
```

### 2. Environment Variables (`.env`)
```bash
# Copy from example
cp .env.example .env

# Key settings for long polling
MIN_WORKERS=50
MAX_WORKERS=1000
POLLING_TIMEOUT=60
POLLING_CHECK_INTERVAL=0.5
TASK_RETENTION_TIME=180
```

## Testing with cURL

### Basic Long Polling Workflow

#### 1. Create Translation Task

**Single Image:**
```bash
# Create task (returns immediately with task_id)
curl -X POST "http://localhost:8000/api/v1/translate" \
  -F "file=@test_image.jpg" \
  -F "target_language=Vietnamese" 

# Response:
# {
#   "task_id": "abc123-def456-789",
#   "status": "pending",
#   "estimated_processing_time": 30
# }
```

**Multiple Images:**
```bash
# Create batch task (1-10 images)
curl -X POST "http://localhost:8000/api/v1/translate" \
  -F "files=@image1.jpg" \
  -F "files=@image2.jpg" \
  -F "files=@image3.jpg" \
  -F "target_language=Vietnamese"

# Response:
# {
#   "task_id": "batch-abc123-def456",
#   "status": "pending", 
#   "estimated_processing_time": 90
# }
```

#### 2. Poll for Results

**Single Image Results:**
```bash
# Long polling (waits up to 60 seconds)
curl "http://localhost:8000/api/v1/result/abc123-def456-789"

# Response (completed):
# {
#   "task_id": "abc123-def456-789",
#   "status": "completed",
#   "success": true,
#   "translated_text": "Văn bản đã dịch",
#   "target_language": "Vietnamese",
#   "processing_time": 25.3
# }
```

**Multiple Images Progressive Results:**
```bash
# Poll for batch results (progressive updates)
curl "http://localhost:8000/api/v1/result/batch-abc123-def456"

# Response (partial completion):
# {
#   "task_id": "batch-abc123-def456",
#   "status": "processing",
#   "partial_results": [
#     {
#       "index": 0,
#       "status": "completed",
#       "translated_text": "Ảnh đầu tiên đã dịch",
#       "completed_at": "2025-01-01T10:30:00Z",
#       "processing_time": 12.5
#     },
#     {
#       "index": 1,
#       "status": "completed", 
#       "translated_text": "Ảnh thứ hai đã dịch",
#       "completed_at": "2025-01-01T10:30:15Z",
#       "processing_time": 15.2
#     },
#     {
#       "index": 2,
#       "status": "processing"
#     }
#   ],
#   "completed_images": 2,
#   "total_images": 3,
#   "progress_percentage": 66.67,
#   "estimated_wait_time": 20
# }
```

### System Monitoring

#### Health Check
```bash
curl http://localhost:8000/health

# Response:
# {
#   "status": "healthy",
#   "service": "image-translation-backend",
#   "version": "1.0.0",
#   "redis_connected": true,
#   "gemini_healthy": true,
#   "api_keys_count": 4
# }
```

#### Queue and Worker Statistics
```bash
curl http://localhost:8000/api/v1/stats

# Response:
# {
#   "queue": {
#     "pending": 25,
#     "processing": 15,
#     "total": 40
#   },
#   "workers": {
#     "total_workers": 75,
#     "active_workers": 15,
#     "idle_workers": 60,
#     "tasks_processed": 1250,
#     "tasks_successful": 1200,
#     "tasks_failed": 50,
#     "success_rate": 96.0
#   },
#   "api_keys": {
#     "total": 4,
#     "active": 3
#   },
#   "capacity_estimate": {
#     "requests_per_minute": 240,
#     "max_workers": 1000,
#     "current_workers": 75
#   }
# }
```

#### Basic Metrics
```bash
curl http://localhost:8000/metrics

# Response:
# {
#   "status": "ok",
#   "redis_connected": true,
#   "active_keys": 3,
#   "total_requests": 1250
# }
```

#### Supported Languages
```bash
curl http://localhost:8000/api/v1/languages

# Response:
# {
#   "supported_languages": [
#     {"code": "vietnamese", "name": "Vietnamese"},
#     {"code": "english", "name": "English"},
#     {"code": "japanese", "name": "Japanese"}
#   ],
#   "default": "Vietnamese"
# }
```

### Load Testing

#### Create Multiple Tasks
```bash
# Create 10 single-image tasks simultaneously
for i in {1..10}; do
  curl -X POST "http://localhost:8000/api/v1/translate" \
    -F "file=@test_image.jpg" \
    -F "target_language=Vietnamese" &
done
wait

# Create multiple batch tasks
for i in {1..5}; do
  curl -X POST "http://localhost:8000/api/v1/translate" \
    -F "files=@image1.jpg" \
    -F "files=@image2.jpg" \
    -F "files=@image3.jpg" \
    -F "target_language=Vietnamese" &
done
wait
```

#### Monitor Auto-Scaling
```bash
# Watch scaling in real-time
watch -n 2 'curl -s http://localhost:8000/api/v1/stats | jq ".workers.total_workers, .queue.pending"'

# Create load and monitor
for i in {1..100}; do
  curl -X POST "http://localhost:8000/api/v1/translate" \
    -F "file=@test.jpg" -F "target_language=Vietnamese" >/dev/null 2>&1 &
  sleep 0.1
done
```

### Advanced Testing

#### Test All Languages
```bash
# Test single image with different languages
languages=("Vietnamese" "English" "Japanese" "Korean" "Spanish")

for lang in "${languages[@]}"; do
  echo "Testing $lang..."
  curl -X POST "http://localhost:8000/api/v1/translate" \
    -F "file=@test_image.jpg" \
    -F "target_language=$lang"
  echo ""
done

# Test multiple images with different languages
for lang in "${languages[@]}"; do
  echo "Testing multiple images with $lang..."
  curl -X POST "http://localhost:8000/api/v1/translate" \
    -F "files=@test1.jpg" \
    -F "files=@test2.jpg" \
    -F "target_language=$lang"
  echo ""
done
```

#### Error Handling Test
```bash
# Test invalid file type (single)
curl -X POST "http://localhost:8000/api/v1/translate" \
  -F "file=@test.txt" \
  -F "target_language=Vietnamese"

# Test invalid file type (multiple)
curl -X POST "http://localhost:8000/api/v1/translate" \
  -F "files=@test.txt" \
  -F "files=@valid.jpg" \
  -F "target_language=Vietnamese"

# Test too many files (>10)
curl -X POST "http://localhost:8000/api/v1/translate" \
  -F "files=@1.jpg" -F "files=@2.jpg" -F "files=@3.jpg" \
  -F "files=@4.jpg" -F "files=@5.jpg" -F "files=@6.jpg" \
  -F "files=@7.jpg" -F "files=@8.jpg" -F "files=@9.jpg" \
  -F "files=@10.jpg" -F "files=@11.jpg" \
  -F "target_language=Vietnamese"

# Test file too large (simulate with large file)
dd if=/dev/zero of=large_file.jpg bs=1M count=60  # 60MB file
curl -X POST "http://localhost:8000/api/v1/translate" \
  -F "file=@large_file.jpg" \
  -F "target_language=Vietnamese"

# Test missing file
curl -X POST "http://localhost:8000/api/v1/translate" \
  -F "target_language=Vietnamese"

# Test invalid task ID
curl "http://localhost:8000/api/v1/result/invalid-task-id"
```

#### Performance Benchmarking
```bash
# Benchmark single image task creation
time for i in {1..50}; do
  curl -s -X POST "http://localhost:8000/api/v1/translate" \
    -F "file=@test.jpg" -F "target_language=Vietnamese" >/dev/null &
done
wait

# Benchmark multiple images task creation
time for i in {1..20}; do
  curl -s -X POST "http://localhost:8000/api/v1/translate" \
    -F "files=@test1.jpg" -F "files=@test2.jpg" -F "files=@test3.jpg" \
    -F "target_language=Vietnamese" >/dev/null &
done
wait

# Mixed workload benchmark
for i in {1..30}; do
  # Single image tasks
  curl -s -X POST "http://localhost:8000/api/v1/translate" \
    -F "file=@single.jpg" -F "target_language=Vietnamese" >/dev/null &
  
  # Multiple images tasks
  curl -s -X POST "http://localhost:8000/api/v1/translate" \
    -F "files=@multi1.jpg" -F "files=@multi2.jpg" \
    -F "target_language=Vietnamese" >/dev/null &
done
wait

# Check final stats
curl -s http://localhost:8000/api/v1/stats | jq '.workers, .queue'
```

## Environment-Specific Configurations

### Development Environment
```bash
# .env settings
DEBUG=true
LOG_LEVEL=DEBUG
MIN_WORKERS=10
MAX_WORKERS=100
POLLING_TIMEOUT=30

# Run with hot reload
uv run uvicorn app.main:app --reload --log-level debug
```

### Staging Environment
```bash
# docker-compose.staging.yml
version: '3.8'
services:
  app:
    build:
      context: .
      dockerfile: docker/Dockerfile
    environment:
      - MIN_WORKERS=25
      - MAX_WORKERS=500
      - LOG_LEVEL=INFO
    ports:
      - "8000:8000"
```

### Production Environment
```bash
# docker-compose.prod.yml
version: '3.8'
services:
  app_prod:
    build:
      context: .
      dockerfile: docker/Dockerfile.prod
    environment:
      - MIN_WORKERS=50
      - MAX_WORKERS=1000
      - LOG_LEVEL=WARNING
    deploy:
      replicas: 3
      restart_policy:
        condition: on-failure
```

## Troubleshooting

### Common Issues

#### Workers Not Scaling
```bash
# Check Redis connection
docker exec -it redis redis-cli ping

# Check queue length
curl -s http://localhost:8000/api/v1/stats | jq '.queue'

# Check logs for scaling events
docker compose logs -f app | grep -i scaling
```

#### API Key Issues
```bash
# Check key status
curl -s http://localhost:8000/api/v1/stats | jq '.api_keys'

# Check individual key health
curl -s http://localhost:8000/health | jq '.api_keys_count'
```

#### Task Processing Stuck
```bash
# Check processing tasks
docker exec -it redis redis-cli smembers processing_tasks

# Check for stale tasks (manual cleanup)
curl -s http://localhost:8000/api/v1/stats | jq '.queue.processing'
```

### Log Analysis
```bash
# View worker activity
docker compose logs app | grep -i worker

# View task processing
docker compose logs app | grep -i task

# View scaling events
docker compose logs app | grep -i scaling

# View error patterns
docker compose logs app | grep -i error
```

## Performance Tuning

### Optimal Settings by Load

#### Light Load (< 1K requests/hour)
```bash
MIN_WORKERS=10
MAX_WORKERS=100
POLLING_CHECK_INTERVAL=1.0
```

#### Medium Load (1K-10K requests/hour)
```bash
MIN_WORKERS=25
MAX_WORKERS=500
POLLING_CHECK_INTERVAL=0.5
```

#### Heavy Load (> 10K requests/hour)
```bash
MIN_WORKERS=50
MAX_WORKERS=1000
POLLING_CHECK_INTERVAL=0.2
```

### Resource Monitoring
```bash
# Check Docker resource usage
docker stats

# Check Redis memory usage
docker exec -it redis redis-cli info memory

# Monitor queue performance
watch -n 1 'curl -s http://localhost:8000/api/v1/stats | jq ".queue, .workers.total_workers"'
```