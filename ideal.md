# Image Translation Backend Requirements

## Project Overview
Create a FastAPI backend service for image translation using Gemini API with intelligent API key rotation and rate limiting.

## Technology Stack
- **Framework**: FastAPI
- **ASGI Server**: Uvicorn (development), Gunicorn + Uvicorn workers (production)
- **Reverse Proxy**: Nginx (production)
- **Cache/Queue**: Redis
- **Containerization**: Docker
- **Logging**: Loguru
- **Environment**: Python 3.11+

## Core Features

### 1. API Key Management
- Load API keys from JSON file with structure:
```json
{
  "keys": [
    {
      "id": "key_1",
      "api_key": "your_gemini_key_here",
      "limits": {
        "requests_per_minute": 60,
        "requests_per_day": 1440,
        "tokens_per_minute": 32000
      }
    }
  ]
}
```

### 2. Smart Key Rotation Strategy
- Use Redis INCR for atomic key selection
- Round-robin rotation ensuring even distribution
- Handle rate limits gracefully with fallback to next available key
- Track usage per key (requests and tokens)
- Automatic key switching when limits are reached

### 3. Async Translation Endpoint
- **Endpoint**: `POST /translate`
- **Input**: 
  - Image file (multipart/form-data)
  - Target language (default: Vietnamese)
- **Output**: JSON response with translated text
- **Features**:
  - Async processing
  - Rate limit handling
  - Quota management
  - Error handling with retry logic

### 4. Translation Logic
Based on the provided Gemini API integration:
- Model: `gemini-2.5-flash-lite`
- Custom prompt for game translation context
- Preserve layout and important terms

### 5. Configuration Management
Create `.env` file structure:
```env
# Server Configuration
SERVER_HOST=0.0.0.0
SERVER_PORT=8000
WORKERS=4
MAX_UPLOAD_SIZE=10485760  # 10MB
REQUEST_TIMEOUT=300  # 5 minutes

# CORS Configuration
CORS_ORIGINS=["http://localhost:3000", "https://yourdomain.com"]
CORS_ALLOW_CREDENTIALS=true

# Rate Limiting (Global)
GLOBAL_RATE_LIMIT=100  # requests per minute per IP
BURST_RATE_LIMIT=20    # burst requests

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# Gemini Configuration
GEMINI_MODEL=gemini-2.5-flash-lite
API_KEYS_FILE=api_keys.json

# Rate Limiting
DEFAULT_RPM=60
DEFAULT_RPD=1440
DEFAULT_TPM=32000

# Logging
LOG_LEVEL=INFO
LOG_ROTATION=00:00
LOG_RETENTION_DAYS=7
```

### 6. Docker Setup
- Multi-stage Dockerfile
- Development and production configurations
- Docker Compose with Redis service
- Health checks
- Volume mounts for logs and config

### 7. Logging Configuration
Using Loguru with:
- Console output with colors (development)
- File rotation (daily)
- Structured logging format
- Different log levels for dev/prod

### 8. Middleware Stack
Essential middleware for production:
- **CORS Middleware**: Handle cross-origin requests
- **Request ID Middleware**: Generate unique request IDs for tracing
- **Rate Limiting Middleware**: Global rate limiting per IP/user
- **Request Timeout Middleware**: Prevent hanging requests
- **File Size Validation Middleware**: Limit image upload size
- **Security Headers Middleware**: Add security headers (HSTS, CSP, etc.)
- **Request Logging Middleware**: Log all requests/responses
- **Error Handling Middleware**: Centralized exception handling
- **Compression Middleware**: Gzip compression for responses

### 9. Nginx Configuration
Production-ready reverse proxy setup:
- **Load Balancing**: Round-robin to multiple app instances
- **Static File Serving**: Direct serving of health check endpoints
- **SSL Termination**: Handle HTTPS certificates
- **Request Buffering**: Buffer large file uploads
- **Rate Limiting**: Additional layer of rate limiting
- **Caching**: Cache static responses and health checks
- **Security**: Request filtering and DDoS protection
- **Logging**: Access logs with custom format

### 10. Error Handling & Monitoring
- Rate limit detection and handling
- Quota exhaustion management
- API key failure recovery
- Health check endpoints
- Metrics endpoint for monitoring

## Project Structure
```
image-translation-backend/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── core/
│   │   ├── config.py
│   │   ├── logging.py
│   │   ├── redis_client.py
│   │   └── security.py
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── cors.py
│   │   ├── rate_limiting.py
│   │   ├── request_id.py
│   │   ├── timeout.py
│   │   ├── file_validation.py
│   │   ├── security_headers.py
│   │   ├── logging.py
│   │   └── error_handler.py
│   ├── services/
│   │   ├── gemini_service.py
│   │   └── key_rotation.py
│   ├── models/
│   │   └── schemas.py
│   └── api/
│       └── routes.py
├── docker/
│   ├── Dockerfile
│   ├── Dockerfile.prod
│   └── docker-compose.yml
├── nginx/
│   ├── nginx.conf
│   ├── sites-available/
│   │   └── image-translation-backend
│   └── ssl/
│       └── .gitkeep
├── config/
│   ├── api_keys.json.example
│   └── gunicorn.conf.py
├── requirements.txt
├── .env.example
├── .dockerignore
└── README.md
```

## Key Implementation Details

### Middleware Implementation Priority
1. **Request ID Middleware**: Generate UUID for request tracing
2. **Security Headers Middleware**: Add OWASP recommended headers
3. **CORS Middleware**: Handle cross-origin requests properly
4. **Rate Limiting Middleware**: Redis-based sliding window
5. **File Validation Middleware**: Check file type, size, and format
6. **Timeout Middleware**: Prevent resource exhaustion
7. **Logging Middleware**: Structure request/response logging
8. **Error Handler Middleware**: Centralized exception handling with proper status codes

### Nginx Configuration Strategy
**Upstream Configuration:**
- Health checks for backend instances
- Failover and load balancing
- Connection pooling and keepalive

**Security Features:**
- Request size limits (client_max_body_size)
- Rate limiting (limit_req_zone)
- IP whitelisting/blacklisting capabilities
- Security headers enforcement

**Performance Optimization:**
- Gzip compression for text responses
- Client-side caching headers
- Connection multiplexing
- Buffer optimization for file uploads

**SSL/TLS Configuration:**
- Modern cipher suites
- HSTS headers
- Certificate auto-renewal ready

### API Key Rotation Algorithm
1. Use Redis counter for atomic key selection
2. Calculate next key index using modulo operation
3. Check key availability and rate limits
4. Implement exponential backoff for failed keys
5. Track per-key metrics in Redis with TTL

### Rate Limiting Strategy
- Track requests per minute/day per key
- Token consumption tracking
- Circuit breaker pattern for failed keys
- Graceful degradation when all keys are limited

### Async Processing
- Use asyncio for concurrent request handling
- Implement request queuing for high load
- Background tasks for cleanup and monitoring

## Deployment Scenarios
1. **Development**: Uvicorn with hot reload, no Nginx
2. **Staging**: Gunicorn + Uvicorn workers behind Nginx
3. **Production**: Multi-instance setup with Nginx load balancing
4. **Containerized**: Docker Compose with Nginx, app, and Redis services

## Security Considerations
- **Input Validation**: Strict file type and size validation
- **Rate Limiting**: Multi-layer (Nginx + Application + Redis)
- **API Key Protection**: Encrypted storage and rotation
- **Request Sanitization**: Prevent injection attacks
- **CORS Policy**: Restrictive cross-origin policy
- **Security Headers**: CSP, HSTS, X-Frame-Options, etc.
- **Error Information**: No sensitive data in error responses

## Performance Optimization
- **Connection Pooling**: Redis and HTTP client pools
- **Async Processing**: Non-blocking I/O operations  
- **Caching**: Response caching for repeated requests
- **Compression**: Gzip compression for large responses
- **Resource Limits**: Memory and CPU constraints
- **Graceful Degradation**: Fallback strategies for high load

## Additional Requirements
- Comprehensive error handling
- Input validation and sanitization
- API documentation with OpenAPI/Swagger
- Unit and integration tests
- Performance monitoring hooks
- Graceful shutdown handling
