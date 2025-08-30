# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a FastAPI backend service for image translation using Gemini API with intelligent API key rotation and rate limiting. The service translates text found in uploaded images to various languages, with Vietnamese as the default target.

## Technology Stack

- **Backend Framework**: FastAPI with async/await patterns
- **ASGI Server**: Uvicorn (dev), Gunicorn + Uvicorn workers (prod)
- **Cache/Queue**: Redis for rate limiting and key rotation
- **API Integration**: Google Generative AI (Gemini)
- **Logging**: Loguru with structured logging and rotation
- **Containerization**: Docker with multi-stage builds
- **Reverse Proxy**: Nginx with rate limiting and load balancing

## Codebase Navigation & Understanding

### Project Index Usage

When working with this codebase, ALWAYS use the project index for architectural awareness:

### 🔍 First Action: Check for Index
```bash
ls PROJECT_INDEX.dsl 2>/dev/null
```

### 📖 Query the Index (DON'T Load Full File)

#### DSL Format Key:
Understanding PROJECT_INDEX.dsl structure:
- `P` - Project metadata (root, indexed_at, file counts)
- `F` - File entries
- `FN file::function` - Function definitions
- `CL file::ClassName` - Class definitions
- `M file::ClassName.method` - Class method definitions
- `C=` - Calls these functions/methods
- `B=` - Called by these functions/methods
- `I` - Imports/dependencies
- `D` - Directory purposes
- `T` - Tree structure
- `MD` - Markdown files with section counts
- `DEP` - Dependencies summary by file

#### Query Examples:
Use grep/ripgrep to query specific information:

```bash
# === FINDING FUNCTIONS & CLASSES ===
# Find specific function or method by name
rg "::FUNCTION_NAME" PROJECT_INDEX.dsl

# Find specific class
rg "^CL.*::CLASS_NAME" PROJECT_INDEX.dsl

# List all functions in a file
grep "^FN PATH/TO/FILE::" PROJECT_INDEX.dsl | cut -d' ' -f2

# List all classes in a file  
grep "^CL PATH/TO/FILE::" PROJECT_INDEX.dsl | cut -d' ' -f2

# List all methods of a class
grep "^M.*::CLASS_NAME\." PROJECT_INDEX.dsl

# Find all functions in specific language
grep "^FN.*\.py::" PROJECT_INDEX.dsl

# Find functions/methods with specific patterns
rg "::(.*PATTERN.*)" PROJECT_INDEX.dsl

# === IMPACT ANALYSIS (Before Changes) ===
# What calls this function? (who depends on it)
rg "B=.*FUNCTION_NAME" PROJECT_INDEX.dsl

# What does this function call?
rg "^FN.*::FUNCTION_NAME.*C=" PROJECT_INDEX.dsl

# Find dead code (functions with no callers)
grep "^FN" PROJECT_INDEX.dsl | grep -v " B="

# === IMPORTS & DEPENDENCIES ===
# Find all imports of a module
rg "^I.*MODULE_NAME" PROJECT_INDEX.dsl | cut -d= -f1

# Check file dependencies
grep "^DEP PATH/TO/FILE" PROJECT_INDEX.dsl

# Find files importing specific library
rg "^I.*=.*LIBRARY_NAME" PROJECT_INDEX.dsl

# === ARCHITECTURE QUERIES ===
# Get directory purposes
grep "^D DIRECTORY_PATH" PROJECT_INDEX.dsl

# View project stats
grep "^P " PROJECT_INDEX.dsl

# See directory tree structure
grep "^T " PROJECT_INDEX.dsl

# Find all parsed files
grep "^F.*parsed=1" PROJECT_INDEX.dsl

# === FILE INFORMATION ===
# Check file language and parse status
grep "^F PATH/TO/FILE" PROJECT_INDEX.dsl

# Find all Python files
grep "^F.*lang=python" PROJECT_INDEX.dsl

# Check markdown documentation
grep "^MD" PROJECT_INDEX.dsl

# === CALL CHAIN TRACING ===
# Find entry points (functions not called by others)
grep "^FN" PROJECT_INDEX.dsl | grep -v " B=" | grep "DIRECTORY_PATTERN"

# Trace what a function calls recursively
# 1. Find what TARGET_FUNCTION() calls:
rg "^FN.*::TARGET_FUNCTION.*C=" PROJECT_INDEX.dsl
# 2. Then find what those functions call, repeat

# === CODE QUALITY ===
# Find functions with many dependencies (high complexity)
grep "^FN" PROJECT_INDEX.dsl | grep "C=" | sort -t'=' -k2 | tail -10

# Find highly coupled functions (called by many)
grep "^FN" PROJECT_INDEX.dsl | grep "B=" | sort -t'=' -k3 | tail -10
```

### 🚫 Critical Rules
- **NEVER load the full PROJECT_INDEX.dsl file** - always query it with grep/rg
- **Start with tree structure** (T entries) to understand project layout
- **Search hierarchy**: PROJECT_INDEX.dsl first, then Claude Code default search
- **Check call relationships** before modifying functions (B= field shows what depends on it)
- **Follow directory purposes** (D entries) when adding new code
- **Verify existing functionality** before implementing duplicates
- **Always indicate usage**: When using PROJECT_INDEX.dsl for navigation, print this line:
  ```
  🗂️ [PROJECT_INDEX] Analyzing codebase structure via PROJECT_INDEX.dsl
  ```

### 🎯 When to Reference
- **Always start with tree structure** at beginning of session or after codebase changes
- Before making any code changes (check dependencies and call relationships)
- When adding new features or functions (find similar existing code)
- During debugging to trace call paths (follow C= and B= chains)
- For architectural decisions (understand directory purposes)

If no PROJECT_INDEX.dsl exists and project has >50 files, suggest running `/index` command first.

## Development Commands

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run Redis (required)
docker run -d -p 6379:6379 redis:8-alpine

# Run development server
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Alternative: run main module directly
python app/main.py
```

### Docker Development
```bash
# Start all services (recommended)
docker compose -f docker/docker-compose.yml up -d

# View logs
docker compose -f docker/docker-compose.yml logs -f app

# Rebuild after changes
docker compose -f docker/docker-compose.yml up --build
```

### Production Deployment
```bash
# Build production image
docker build -f docker/Dockerfile.prod -t image-translate-backend:prod .

# Run with production config (uncomment prod services in docker-compose.yml)
docker compose -f docker/docker-compose.yml up -d nginx app_prod redis
```

## Architecture Overview

### Core Components

1. **Main Application** (`app/main.py`)
   - FastAPI app with comprehensive middleware stack
   - Lifespan events for startup/shutdown
   - Health checks and metrics endpoints

2. **Middleware Pipeline** (order matters - executed in reverse order of addition)
   - Error handling (outermost)
   - Request logging
   - Timeout handling
   - File validation  
   - Rate limiting (Redis-based)
   - CORS
   - Security headers
   - Request ID generation
   - Gzip compression (innermost)

3. **Services Layer**
   - `GeminiTranslationService`: Handles API calls to Gemini with retry logic
   - `APIKeyManager`: Smart rotation with rate limiting and failure handling

4. **Redis Integration**
   - Rate limiting counters with atomic operations
   - API key usage tracking (RPM/RPD/TPM)
   - Key rotation state management
   - Connection pooling with automatic retries

### Key Design Patterns

#### API Key Rotation Strategy
- Uses Redis INCR for atomic key selection
- Round-robin with rate limit awareness
- Circuit breaker pattern for failed keys
- Exponential backoff on failures
- Per-key metrics tracking with TTL

#### Rate Limiting Implementation
- Multi-layer: Nginx + Application + Redis
- Sliding window using Redis with atomic operations  
- Different limits for different endpoints
- Burst handling with token bucket concept

#### Error Handling
- Comprehensive middleware for unhandled exceptions
- Structured error responses with request IDs
- Different retry strategies for different error types
- Graceful degradation when external services fail

## Configuration Management

### Required Setup Files

1. **API Keys** (`config/api_keys.json`):
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

2. **Environment** (`.env`):
Copy from `.env.example` and configure Redis, rate limits, and server settings.

### Key Configuration Areas

- **Server Settings**: Host, port, worker count, timeouts
- **Rate Limiting**: Global limits, burst limits, per-endpoint limits
- **Redis**: Connection details, pooling settings
- **Gemini API**: Model selection, safety settings
- **Logging**: Levels, rotation, retention

## Important Implementation Details

### File Processing
- Supports multiple image formats (JPEG, PNG, GIF, WebP, BMP, TIFF)
- Uses python-magic for MIME type detection
- PIL for image processing and format conversion
- Size limits enforced at multiple levels (Nginx, middleware, application)

### Security Considerations
- All file uploads validated for type and size
- OWASP security headers implemented
- Input sanitization and validation
- No sensitive data in error responses
- Request timeout handling to prevent resource exhaustion

### Performance Optimizations
- Async/await throughout the application
- Connection pooling for Redis
- Image resizing for large uploads
- Gzip compression for responses
- Request buffering for large file uploads

### Monitoring and Observability
- Structured logging with request tracing
- Health checks for all components
- Metrics endpoints for monitoring
- Response time tracking
- Rate limit monitoring

## Common Development Tasks

### Adding New Middleware
Add to `app/main.py` in reverse order of execution (last added executes first).

### Modifying Rate Limits
Update configuration in `.env` or per-endpoint limits in Nginx config.

### Adding New Languages
Add to `TranslationLanguage` enum in `app/models/schemas.py`.

### Debugging Issues
- Check logs in `logs/` directory or Docker logs
- Use `/health` endpoint for component status
- Monitor Redis keys for rate limiting state
- Check API key rotation with Redis CLI

### Testing API Endpoints
```bash
# Health check
curl http://localhost:8000/health

# Translation test
curl -X POST "http://localhost:8000/api/v1/translate" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@test_image.jpg" \
  -F "target_language=Vietnamese"

# Get supported languages
curl http://localhost:8000/api/v1/languages
```

## File Structure Significance

- `app/core/`: Foundation components (config, logging, Redis)
- `app/middleware/`: Request/response processing pipeline  
- `app/services/`: Business logic and external API integration
- `app/models/`: Pydantic schemas for request/response validation
- `app/api/`: HTTP route handlers
- `docker/`: Container configurations for different environments
- `nginx/`: Production reverse proxy configuration
- `config/`: Application configuration files