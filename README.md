# Image Translation Backend

A high-performance FastAPI backend service for image translation using Gemini API with intelligent API key rotation and rate limiting.

## Features

- 🚀 **FastAPI Framework**: High-performance async API with automatic OpenAPI documentation
- 🔄 **Smart API Key Rotation**: Intelligent rotation with rate limit handling and fallback
- 📸 **Multiple Images**: Process 1-10 images per request with progressive results
- ⏱️ **Long Polling**: Real-time results with auto-scaling worker pools (50-1000 workers)
- 🛡️ **Comprehensive Security**: Multi-layer rate limiting, security headers, input validation
- 📊 **Redis Integration**: Caching, rate limiting, and key usage tracking
- 🐳 **Production Ready**: Docker containerization with Nginx reverse proxy
- 🌍 **Multi-Language Support**: Support for 13+ languages including Vietnamese, English, Japanese
- 📝 **Structured Logging**: Comprehensive logging with Loguru and request tracking
- 🔧 **Middleware Stack**: Complete middleware pipeline for production deployment

## Quick Start

### 1. Setup API Keys

Copy the example configuration and add your Gemini API keys:

```bash
cp config/api_keys.json.example config/api_keys.json
```

Edit `config/api_keys.json` with your actual Gemini API keys:

```json
{
  "keys": [
    {
      "id": "key_1",
      "api_key": "your_actual_gemini_api_key",
      "limits": {
        "requests_per_minute": 60,
        "requests_per_day": 1440,
        "tokens_per_minute": 32000
      }
    }
  ]
}
```

### 2. Environment Configuration

Copy and configure environment variables:

```bash
cp .env.example .env
```

### 3. Run with Docker (Recommended)

```bash
# Start all services (app + Redis)
docker compose -f docker/docker-compose.yml up -d

# View logs
docker compose -f docker/docker-compose.yml logs -f app
```

### 4. Run Locally

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Start Redis (required)
docker run -d -p 6379:6379 redis:8-alpine

# Run the application
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## API Endpoints

### Translation

**POST** `/api/v1/translate`

Translate text in uploaded image(s) to target language with long polling.

**Parameters:**
- `file`: Single image file (JPG, PNG, GIF, WebP, BMP, TIFF) OR
- `files`: Multiple image files (1-10 images, max 50MB total)
- `target_language`: Target language (default: Vietnamese)

**Single Image Example:**
```bash
curl -X POST "http://localhost:8000/api/v1/translate" \
  -F "file=@image.jpg" \
  -F "target_language=Vietnamese"
```

**Multiple Images Example:**
```bash
curl -X POST "http://localhost:8000/api/v1/translate" \
  -F "files=@image1.jpg" \
  -F "files=@image2.jpg" \
  -F "files=@image3.jpg" \
  -F "target_language=Vietnamese"
```

**Response (Task Created):**
```json
{
  "task_id": "abc123-def456-789",
  "status": "pending",
  "estimated_processing_time": 45
}
```

### Get Results

**GET** `/api/v1/result/{task_id}`

Poll for translation results with progressive updates.

**Example:**
```bash
curl "http://localhost:8000/api/v1/result/abc123-def456-789"
```

**Response (Single Image - Completed):**
```json
{
  "task_id": "abc123-def456-789",
  "status": "completed",
  "success": true,
  "translated_text": "Translated content here",
  "target_language": "Vietnamese",
  "processing_time": 25.3
}
```

**Response (Multiple Images - Progressive):**
```json
{
  "task_id": "abc123-def456-789",
  "status": "processing",
  "partial_results": [
    {
      "index": 0,
      "status": "completed",
      "translated_text": "First image text",
      "completed_at": "2025-01-01T10:30:00Z"
    },
    {
      "index": 1,
      "status": "processing"
    },
    {
      "index": 2,
      "status": "pending"
    }
  ],
  "completed_images": 1,
  "total_images": 3,
  "progress_percentage": 33.33
}
```

### Health Check

**GET** `/health`

Service health status with component checks.

### API Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Supported Languages

- Vietnamese (default)
- English
- Japanese
- Korean  
- Chinese (Simplified)
- Chinese (Traditional)
- Spanish
- French
- German
- Portuguese
- Russian
- Thai
- Indonesian

## Architecture

### Components

1. **FastAPI Application** (`app/main.py`)
   - Main application with middleware stack
   - Async request handling with lifespan management

2. **Middleware Pipeline** (`app/middleware/`)
   - Request ID generation
   - Security headers (OWASP recommended)
   - Rate limiting (Redis-based)
   - File validation
   - Request timeout handling
   - Structured logging
   - Error handling

3. **Services** (`app/services/`)
   - **Gemini Service**: API integration with retry logic
   - **Key Rotation**: Smart API key management

4. **Core** (`app/core/`)
   - Configuration management
   - Redis client with connection pooling
   - Logging setup with rotation

### Key Features

#### Smart API Key Rotation

- Atomic key selection using Redis counters
- Rate limit tracking per key (RPM, RPD, TPM)
- Automatic failover on quota/error limits
- Circuit breaker pattern for failed keys

#### Security

- Multi-layer rate limiting (Nginx + Application + Redis)
- OWASP security headers
- Input validation and sanitization
- File type verification with python-magic
- Request size limits

#### Performance

- Async/await throughout
- Connection pooling (Redis, HTTP)
- Gzip compression
- Request buffering for large uploads
- Graceful degradation strategies

## Development

### Project Structure

```
image-translation-backend/
├── app/
│   ├── main.py              # FastAPI application
│   ├── core/                # Core components
│   │   ├── config.py        # Configuration management
│   │   ├── logging.py       # Logging setup
│   │   └── redis_client.py  # Redis client
│   ├── middleware/          # Middleware components
│   ├── services/            # Business logic services
│   ├── models/              # Pydantic models
│   └── api/                 # API routes
├── docker/                  # Docker configuration
├── nginx/                   # Nginx configuration  
├── config/                  # Configuration files
└── pyproject.toml           # Project dependencies and configuration
```

### Running Tests

```bash
# Install development dependencies (including test dependencies)
uv sync --dev

# Run tests (when implemented)
uv run pytest
```

### Code Quality

```bash
# Format code (if you add these tools to dev dependencies)
uv run black app/
uv run isort app/

# Lint (if you add these tools to dev dependencies)  
uv run flake8 app/
uv run mypy app/
```

## Production Deployment

### Docker Production Setup

1. **Build production image:**
```bash
docker build -f docker/Dockerfile.prod -t image-translate-backend:prod .
```

2. **Configure environment:**
   - Set production environment variables
   - Configure SSL certificates in `nginx/ssl/`
   - Update `docker-compose.yml` for production services

3. **Deploy with Nginx:**
```bash
# Enable production services in docker-compose.yml
# Uncomment nginx and app_prod services
docker compose -f docker/docker-compose.yml up -d nginx app_prod redis
```

### Scaling

- **Horizontal**: Add more app containers behind Nginx load balancer
- **Vertical**: Increase worker count in gunicorn config
- **Redis**: Use Redis Cluster for high availability

### Monitoring

- Health endpoint: `/health`
- Metrics endpoint: `/metrics`
- Structured logs with request tracing
- Response time tracking

## Configuration

### Environment Variables

Key configuration options:

```bash
# Server
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
WORKERS=4

# Rate Limiting
GLOBAL_RATE_LIMIT=100
BURST_RATE_LIMIT=20

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Gemini
GEMINI_MODEL=gemini-2.5-flash-lite
API_KEYS_FILE=config/api_keys.json
```

### API Key Limits

Configure per-key limits in `config/api_keys.json`:

```json
{
  "limits": {
    "requests_per_minute": 60,    # API requests per minute
    "requests_per_day": 1440,     # API requests per day  
    "tokens_per_minute": 32000    # Token consumption per minute
  }
}
```

## Troubleshooting

### Common Issues

1. **Redis Connection Failed**
   - Ensure Redis is running: `docker run -d -p 6379:6379 redis:8-alpine`
   - Check Redis configuration in `.env`

2. **API Key Errors**
   - Verify API keys in `config/api_keys.json`
   - Check Google Cloud Console for key status
   - Review rate limits and quotas

3. **File Upload Errors**
   - Check file size limits (`MAX_UPLOAD_SIZE`)
   - Verify supported file types
   - Ensure proper Content-Type headers

4. **Rate Limiting**
   - Check Redis key expiration
   - Adjust rate limits in configuration
   - Monitor logs for rate limit violations

### Logs

View application logs:

```bash
# Docker
docker compose -f docker/docker-compose.yml logs -f app

# Local
tail -f logs/app_$(date +%Y-%m-%d).log
```

## License

MIT License - see LICENSE file for details.

## Support

For issues and feature requests, please create an issue in the project repository.