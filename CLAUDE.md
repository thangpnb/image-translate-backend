# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FastAPI backend for image translation using Gemini API with long polling architecture and distributed auto-scaling worker pools (50-1000 workers). Supports 3K-60K requests/minute with Redis-based cluster coordination and asynchronous processing.

## Technology Stack

- **Backend Framework**: FastAPI with async/await patterns
- **ASGI Server**: Uvicorn (dev), Gunicorn + Uvicorn workers (prod)
- **Cache/Queue**: Redis for rate limiting, key rotation, task storage, job queue management, and distributed worker coordination
- **API Integration**: Google Generative AI (Gemini)
- **Logging**: Loguru with structured logging and rotation
- **Containerization**: Docker with multi-stage builds
- **Reverse Proxy**: Nginx with rate limiting and load balancing

## Development Commands

### Local Development
```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Run Redis (required)
docker run -d -p 6379:6379 redis:8-alpine

# Run development server
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Alternative: run main module directly
uv run python app/main.py

# Install development dependencies
uv sync --dev

# Run tests
uv run pytest
```

### Docker Development
```bash
# Start all services (first time)
docker compose -f docker/docker-compose.yml up -d

# When modifying Python code (.py files)
# → NO action needed, uvicorn --reload automatically reloads

# When changing config files
docker compose -f docker/docker-compose.yml restart app

# When changing pyproject.toml/uv.lock  
docker compose -f docker/docker-compose.yml build app
docker compose -f docker/docker-compose.yml up -d

# When changing Dockerfile
docker compose -f docker/docker-compose.yml up -d --build
```

### Production Deployment
```bash
# Build production image
docker build -f docker/Dockerfile.prod -t image-translate-backend:prod .

# Run with production config (uncomment prod services in docker-compose.yml)
docker compose -f docker/docker-compose.yml up -d nginx app_prod redis
```

## Architecture Overview

### Workflow
1. `POST /api/v1/translate` → Returns `task_id` immediately
2. Worker pool processes tasks from Redis queue using Gemini API
3. `GET /api/v1/translate/result/{task_id}` → Long polling (0.5s intervals, 60s timeout)

### Core Components
- **Task Manager** (`app/services/task_manager.py`): Redis task storage and queue
- **Distributed Worker Pool** (`app/services/worker_pool.py`): Auto-scaling 50-1000 workers with Redis-based cluster coordination
- **Gemini Service** (`app/services/gemini_service.py`): API calls with retry logic
- **API Key Manager** (`app/services/key_rotation.py`): Smart rotation and rate limiting

### Scaling & Performance
- **Distributed Auto-scaling**: Gradual scaling (+5/10/15/25 workers) with hysteresis and cooldown mechanisms
- **Cluster Coordination**: Leader election via Redis locks, instance heartbeats, stale worker cleanup
- **API Key Rotation**: Round-robin with real-time Redis state and failure handling
- **Redis**: Task storage, FIFO queue, rate limiting, connection pooling, and distributed state management
- **Error Handling**: Retry logic, circuit breaker pattern, graceful degradation

### Distributed Architecture
- **Instance Registration**: Each instance registers with unique ID (`instance-{hostname}-{uuid}`)
- **Worker Coordination**: All workers registered in `cluster:active_workers` Redis set
- **Scaling Decisions**: Leader election via `cluster:scaling_lock` for coordinated decisions
- **Capacity Calculation**: Real-time API key availability from Redis state
- **Hysteresis**: 3 consecutive low queue readings required before scale-down
- **Cooldown**: 30-second cooldown between major scaling events (>20 workers)
- **Health Monitoring**: Instance heartbeats every 30s, automatic stale cleanup after 3 minutes

## Configuration Management

### Required Setup Files

1. **API Keys** (`config/api_keys.yaml`):
```yaml
keys:
  - id: key_1
    api_key: your_gemini_api_key_here
  - id: key_2
    api_key: your_gemini_api_key_here_2
```

2. **Environment** (`.env`):
Copy from `.env.example` and configure Redis, **global rate limits** (DEFAULT_RPM, DEFAULT_RPD, DEFAULT_TPM), and server settings.

### Key Configuration Areas
- **Worker Pool**: MIN_WORKERS (50), MAX_WORKERS (1000)
- **Long Polling**: POLLING_TIMEOUT (60s), CHECK_INTERVAL (0.5s)  
- **Task Management**: RETENTION_TIME (24h), cleanup intervals
- **Redis**: Connection, pooling, queue settings
- **Rate Limiting**: Global/per-endpoint limits

## Key Features
- **File Support**: JPEG, PNG, GIF, WebP, BMP, TIFF with size validation
- **Multiple Images**: 1-10 images per request with progressive results
- **Security**: Input validation, OWASP headers, timeout handling
- **Monitoring**: Task tracking, worker metrics, queue statistics, auto-cleanup
- **Performance**: Async processing, connection pooling, image optimization

## Development Tasks

### Adding Components
- **Middleware**: Add to `app/main.py` (reverse execution order)
- **Languages**: Add to both `TranslationLanguage` enum in `app/models/schemas.py` and prompts in `config/prompts.yaml`
- **Rate Limits**: Update `.env` or Nginx config

### Debugging
- **Task Status**: `/api/v1/translate/result/{task_id}` 
- **Queue Stats**: `/stats`
- **Health**: `/health` endpoint
- **Redis Keys**: Core: `tasks:*`, `translation_queue`, `processing_tasks`; Distributed: `cluster:active_instances`, `cluster:active_workers`, `cluster:scaling_lock`, `instance:heartbeat:*`
- **Logs**: `logs/` directory or Docker logs

### Testing API Endpoints
```bash
# Single image (existing)
curl -X POST "http://localhost:8000/api/v1/translate" \
  -F "file=@test.jpg" -F "target_language=Vietnamese"

# Multiple images (new feature)
curl -X POST "http://localhost:8000/api/v1/translate" \
  -F "files=@image1.jpg" -F "files=@image2.jpg" -F "target_language=Vietnamese"

# Poll result (60s timeout, progressive results)
curl "http://localhost:8000/api/v1/translate/result/{task_id}"

# Check stats
curl http://localhost:8000/stats

# Health check  
curl http://localhost:8000/health
```

## File Structure
- `app/core/`: Config, logging, Redis client
- `app/services/`: 
  - `task_manager.py`: Redis task storage and queue
  - `worker_pool.py`: Distributed auto-scaling worker pool (50-1000) with Redis coordination
  - `gemini_service.py`: API integration with retry
  - `key_rotation.py`: API key management
- `app/models/`: Task schemas (`TaskStatus`, `TranslationTask`, responses)
- `app/api/`: Routes (`/translate` → task creation, `/translate/result/{id}` → polling, `/stats`)

## Performance
- **Throughput**: 3K-60K requests/minute (depends on API keys)
- **Workers**: 50-1000 auto-scaling based on queue length
- **Processing**: Sub-second task creation, 30-60s translation time
- **Storage**: 24h task retention, automatic cleanup every 5 minutes