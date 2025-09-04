# API Documentation

## Base URL
```
http://localhost:8000
```

## Authentication
No authentication required.

## Endpoints

### 1. Submit Translation Task

**Endpoint:** `POST /api/v1/translate`

**Description:** Submit one or multiple images for translation. Returns a task ID immediately for polling results.

**Content-Type:** `multipart/form-data`

#### Single Image Request

```bash
curl -X POST "http://localhost:8000/api/v1/translate" \
  -F "file=@image.jpg" \
  -F "target_language=Vietnamese"
```

#### Multiple Images Request

```bash
curl -X POST "http://localhost:8000/api/v1/translate" \
  -F "files=@image1.jpg" \
  -F "files=@image2.jpg" \
  -F "files=@image3.jpg" \
  -F "target_language=Vietnamese"
```

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | File | Yes* | Single image file (for single image translation) |
| `files` | File[] | Yes* | Multiple image files (for batch translation) |
| `target_language` | String | Yes | Target language for translation |

*Either `file` or `files` is required, not both.

#### Supported Languages
- English
- Vietnamese
- Spanish
- French
- German
- Japanese
- Korean
- Chinese (Simplified)
- Chinese (Traditional)
- Thai
- Indonesian
- Portuguese
- Russian
- Italian
- Dutch
- Arabic
- Hindi

#### Supported File Formats
- JPEG (.jpg, .jpeg)
- PNG (.png)
- GIF (.gif)
- WebP (.webp)
- BMP (.bmp)
- TIFF (.tiff, .tif)

#### File Constraints
- Maximum file size: 10MB per image
- Maximum number of images: 10 per request
- Supported dimensions: Up to 4096x4096 pixels

#### Response

**Status Code:** `200 OK`

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "estimated_processing_time": 0
}
```

**Status Code:** `400 Bad Request`

```json
{
  "detail": "Invalid file format. Supported formats: JPEG, PNG, GIF, WebP, BMP, TIFF"
}
```

```json
{
  "detail": "File size exceeds maximum limit of 10MB"
}
```

```json
{
  "detail": "Maximum 10 images allowed per request"
}
```

**Status Code:** `422 Unprocessable Entity`

```json
{
  "detail": [
    {
      "loc": ["body", "target_language"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### 2. Get Translation Result

**Endpoint:** `GET /api/v1/translate/result/{task_id}`

**Description:** Poll for translation results. Uses long polling with 60-second timeout and 0.5-second check intervals.

```bash
curl "http://localhost:8000/api/v1/translate/result/550e8400-e29b-41d4-a716-446655440000"
```

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_id` | String | Yes | UUID of the translation task |

#### Response - Pending

**Status Code:** `200 OK`

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "success": null,
  "partial_results": [],
  "completed_images": 0,
  "total_images": 1,
  "target_language": "Vietnamese",
  "created_at": "2025-09-04T16:19:24.102280Z",
  "started_at": null,
  "completed_at": null,
  "processing_time": null,
  "error": null,
  "estimated_wait_time": 10
}
```

#### Response - Processing

**Status Code:** `200 OK`

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "success": null,
  "partial_results": [
    {
      "index": 0,
      "status": "completed",
      "translated_text": "Translated text from first image",
      "error": null,
      "completed_at": "2025-09-04T16:19:25.694578Z",
      "processing_time": 1.589926
    },
    {
      "index": 1,
      "status": "processing",
      "translated_text": null,
      "error": null,
      "completed_at": null,
      "processing_time": null
    }
  ],
  "completed_images": 1,
  "total_images": 2,
  "target_language": "Vietnamese",
  "created_at": "2025-09-04T16:19:24.102280Z",
  "started_at": "2025-09-04T16:19:24.104652Z",
  "completed_at": null,
  "processing_time": null,
  "error": null,
  "estimated_wait_time": null
}
```

#### Response - Completed (Single Image)

**Status Code:** `200 OK`

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "success": true,
  "partial_results": [
    {
      "index": 0,
      "status": "completed",
      "translated_text": "Xin chào thế giới!\nĐây là văn bản được dịch từ hình ảnh.",
      "error": null,
      "completed_at": "2025-09-04T16:19:25.694578Z",
      "processing_time": 1.589926
    }
  ],
  "completed_images": 1,
  "total_images": 1,
  "target_language": "Vietnamese",
  "created_at": "2025-09-04T16:19:24.102280Z",
  "started_at": "2025-09-04T16:19:24.104652Z",
  "completed_at": "2025-09-04T16:19:25.694624Z",
  "processing_time": 1.589972,
  "error": null,
  "estimated_wait_time": null
}
```

#### Response - Completed (Multiple Images)

**Status Code:** `200 OK`

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "success": true,
  "partial_results": [
    {
      "index": 0,
      "status": "completed",
      "translated_text": "Xin chào thế giới!",
      "error": null,
      "completed_at": "2025-09-04T16:19:25.694578Z",
      "processing_time": 1.589926
    },
    {
      "index": 1,
      "status": "completed",
      "translated_text": "Đây là hình ảnh thứ hai",
      "error": null,
      "completed_at": "2025-09-04T16:19:26.894578Z",
      "processing_time": 2.789926
    }
  ],
  "completed_images": 2,
  "total_images": 2,
  "target_language": "Vietnamese",
  "created_at": "2025-09-04T16:19:24.102280Z",
  "started_at": "2025-09-04T16:19:24.104652Z",
  "completed_at": "2025-09-04T16:19:26.894624Z",
  "processing_time": 2.789972,
  "error": null,
  "estimated_wait_time": null
}
```

#### Response - Failed

**Status Code:** `200 OK`

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "failed",
  "success": false,
  "partial_results": [
    {
      "index": 0,
      "status": "failed",
      "translated_text": null,
      "error": "Unable to extract text from image",
      "completed_at": "2025-09-04T16:19:25.694578Z",
      "processing_time": 1.589926
    }
  ],
  "completed_images": 1,
  "total_images": 1,
  "target_language": "Vietnamese",
  "created_at": "2025-09-04T16:19:24.102280Z",
  "started_at": "2025-09-04T16:19:24.104652Z",
  "completed_at": "2025-09-04T16:19:25.694624Z",
  "processing_time": 1.589972,
  "error": "Unable to extract text from image",
  "estimated_wait_time": null
}
```

#### Response - Task Not Found

**Status Code:** `404 Not Found`

```json
{
  "detail": "Task not found or has expired"
}
```

### 3. Get System Statistics

**Endpoint:** `GET /stats`

**Description:** Get current system statistics including queue status and worker information.

```bash
curl "http://localhost:8000/stats"
```

#### Response

**Status Code:** `200 OK`

```json
{
  "queue": {
    "pending": 0,
    "processing": 0,
    "total": 0
  },
  "workers": {
    "total_workers": 50,
    "active_workers": 0,
    "idle_workers": 50,
    "tasks_processed": 3,
    "tasks_successful": 3,
    "tasks_failed": 0,
    "success_rate": 100.0
  },
  "api_keys": {
    "total": 4,
    "active": 4
  },
  "capacity_estimate": {
    "requests_per_minute": 240,
    "max_workers": 1000,
    "current_workers": 50
  }
}
```

### 4. Health Check

**Endpoint:** `GET /health`

**Description:** Check if the service is healthy and operational.

```bash
curl "http://localhost:8000/health"
```

#### Response

**Status Code:** `200 OK`

```json
{
  "status": "healthy",
  "service": "image-translation-backend",
  "version": "1.0.0",
  "redis_connected": true,
  "gemini_healthy": true,
  "api_keys_count": 4
}
```

**Status Code:** `200 OK` (Note: Service returns 200 even when unhealthy)

```json
{
  "status": "unhealthy",
  "service": "image-translation-backend",
  "version": "1.0.0",
  "redis_connected": false,
  "gemini_healthy": false,
  "api_keys_count": 0
}
```

## Error Codes

| Code | Description |
|------|-------------|
| `INVALID_FILE_FORMAT` | Unsupported file format |
| `FILE_TOO_LARGE` | File exceeds size limit |
| `TOO_MANY_FILES` | Exceeds maximum file count |
| `EXTRACTION_FAILED` | Unable to extract text from image |
| `TRANSLATION_FAILED` | Translation service error |
| `RATE_LIMIT_EXCEEDED` | Too many requests |
| `SERVICE_UNAVAILABLE` | External service temporarily unavailable |

## Rate Limits

- **Global Rate Limit:** 1000 requests per minute
- **Per IP Rate Limit:** 100 requests per minute
- **File Upload Rate Limit:** 50 MB per minute per IP

When rate limit is exceeded:

**Status Code:** `429 Too Many Requests`

```json
{
  "detail": "Rate limit exceeded. Try again later.",
  "retry_after": 60
}
```

## Long Polling Behavior

The `/translate/result/{task_id}` endpoint uses long polling:

- **Timeout:** 60 seconds maximum
- **Check Interval:** 0.5 seconds
- **Progressive Results:** For multiple images, partial results may be returned as they complete
- **Connection:** Keep-alive for efficient polling

## Example Workflow

### 1. Submit Translation Task

```bash
curl -X POST "http://localhost:8000/api/v1/translate" \
  -F "file=@document.jpg" \
  -F "target_language=Vietnamese"
```

Response:
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "estimated_processing_time": 0
}
```

### 2. Poll for Results

```bash
curl "http://localhost:8000/api/v1/translate/result/550e8400-e29b-41d4-a716-446655440000"
```

### 3. Receive Completed Result

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "success": true,
  "partial_results": [
    {
      "index": 0,
      "status": "completed",
      "translated_text": "Đây là văn bản được dịch từ tài liệu hình ảnh.",
      "error": null,
      "completed_at": "2025-09-04T16:19:25.694578Z",
      "processing_time": 1.589926
    }
  ],
  "completed_images": 1,
  "total_images": 1,
  "target_language": "Vietnamese",
  "created_at": "2025-09-04T16:19:24.102280Z",
  "started_at": "2025-09-04T16:19:24.104652Z",
  "completed_at": "2025-09-04T16:19:25.694624Z",
  "processing_time": 1.589972,
  "error": null,
  "estimated_wait_time": null
}
```

## Performance Notes

- **Task Creation:** Sub-second response time
- **Translation Processing:** 30-60 seconds average (depends on image complexity)
- **Concurrent Processing:** 50-1000 workers auto-scaling based on load
- **Data Retention:** Results stored for 24 hours, then automatically cleaned up
- **Throughput:** 3,000-60,000 requests per minute (depending on API key availability)