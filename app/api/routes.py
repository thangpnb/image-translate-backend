import time
import asyncio
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request, Path
from fastapi.responses import JSONResponse
import magic
from loguru import logger
from ..models.schemas import (
    TranslationResponse, 
    ErrorResponse, 
    HealthResponse, 
    MetricsResponse,
    TranslationLanguage,
    TaskCreationResponse,
    TaskResultResponse,
    TaskStatus
)
from ..services.gemini_service import gemini_service
from ..services.key_rotation import api_key_manager
from ..services.task_manager import task_manager
from ..services.worker_pool import worker_pool
from ..core.redis_client import redis_client
from ..core.config import settings

router = APIRouter()

# Allowed image MIME types
ALLOWED_MIME_TYPES = {
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/webp',
    'image/bmp',
    'image/tiff'
}


@router.post("/translate", response_model=TaskCreationResponse)
async def create_translation_task(
    request: Request,
    file: UploadFile = File(..., description="Image file to translate"),
    target_language: TranslationLanguage = Form(
        default=TranslationLanguage.VIETNAMESE,
        description="Target language for translation"
    )
):
    """
    Create a translation task and return task_id for polling
    """
    request_id = getattr(request.state, 'request_id', 'unknown')
    
    logger.info(f"Translation task creation request", extra={
        "request_id": request_id,
        "filename": file.filename,
        "content_type": file.content_type,
        "target_language": target_language.value
    })
    
    try:
        # Validate file
        if not file:
            raise HTTPException(status_code=400, detail="No file provided")
        
        # Read file content
        file_content = await file.read()
        file_size = len(file_content)
        
        # Check file size
        if file_size > settings.MAX_UPLOAD_SIZE:
            logger.warning(f"File too large: {file_size} bytes", extra={"request_id": request_id})
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size: {settings.MAX_UPLOAD_SIZE} bytes"
            )
        
        # Validate file type using python-magic
        try:
            mime_type = magic.from_buffer(file_content, mime=True)
        except Exception as e:
            logger.error(f"Failed to detect file type: {e}", extra={"request_id": request_id})
            raise HTTPException(status_code=400, detail="Unable to detect file type")
        
        if mime_type not in ALLOWED_MIME_TYPES:
            logger.warning(f"Invalid file type: {mime_type}", extra={"request_id": request_id})
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type: {mime_type}. Allowed types: {', '.join(ALLOWED_MIME_TYPES)}"
            )
        
        logger.info(f"File validation passed", extra={
            "request_id": request_id,
            "file_size": file_size,
            "mime_type": mime_type
        })
        
        # Create translation task
        task = await task_manager.create_task(file_content, target_language.value)
        
        # Estimate processing time based on current queue length
        estimated_wait_time = await task_manager.estimate_wait_time()
        
        logger.info(f"Created translation task {task.task_id}", extra={
            "request_id": request_id,
            "task_id": task.task_id,
            "target_language": target_language.value,
            "estimated_wait_time": estimated_wait_time
        })
        
        return TaskCreationResponse(
            task_id=task.task_id,
            status=TaskStatus.PENDING,
            estimated_processing_time=estimated_wait_time
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating translation task: {e}", extra={
            "request_id": request_id
        })
        raise HTTPException(status_code=500, detail="Failed to create translation task")


@router.get("/result/{task_id}", response_model=TaskResultResponse)
async def get_translation_result(
    task_id: str = Path(..., description="Task ID to check"),
    timeout: int = 60
):
    """
    Get translation result with long polling support
    """
    if timeout > settings.POLLING_TIMEOUT:
        timeout = settings.POLLING_TIMEOUT
    
    start_time = time.time()
    
    logger.info(f"Polling request for task {task_id} with timeout {timeout}s")
    
    try:
        while time.time() - start_time < timeout:
            # Get current task status
            task = await task_manager.get_task(task_id)
            
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")
            
            # If task is completed or failed, return immediately
            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                success = task.status == TaskStatus.COMPLETED
                
                logger.info(f"Task {task_id} final status: {task.status.value}")
                
                return TaskResultResponse(
                    task_id=task.task_id,
                    status=task.status,
                    success=success,
                    translated_text=task.translated_text,
                    target_language=task.target_language,
                    created_at=task.created_at,
                    started_at=task.started_at,
                    completed_at=task.completed_at,
                    processing_time=task.processing_time,
                    error=task.error
                )
            
            # Task is still pending or processing, wait before checking again
            await asyncio.sleep(settings.POLLING_CHECK_INTERVAL)
        
        # Timeout reached, return current status with estimated wait time
        task = await task_manager.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        estimated_wait_time = await task_manager.estimate_wait_time()
        
        logger.info(f"Polling timeout for task {task_id}, status: {task.status.value}")
        
        return TaskResultResponse(
            task_id=task.task_id,
            status=task.status,
            success=None,
            translated_text=None,
            target_language=task.target_language,
            created_at=task.created_at,
            started_at=task.started_at,
            completed_at=None,
            processing_time=None,
            error=None,
            estimated_wait_time=estimated_wait_time
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error polling task {task_id}: {e}")
        raise HTTPException(status_code=500, detail="Error checking task status")


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Comprehensive health check endpoint
    """
    try:
        # Check Redis connection
        redis_connected = False
        if redis_client.redis:
            try:
                await redis_client.redis.ping()
                redis_connected = True
            except Exception:
                pass
        
        # Check Gemini service
        gemini_healthy, gemini_status = await gemini_service.health_check()
        
        # Get API keys count
        api_keys_count = len(api_key_manager.keys)
        
        status = "healthy"
        if not redis_connected:
            status = "degraded"
        if not gemini_healthy:
            status = "unhealthy"
        if api_keys_count == 0:
            status = "unhealthy"
        
        logger.info(f"Health check: {status}", extra={
            "redis_connected": redis_connected,
            "gemini_healthy": gemini_healthy,
            "api_keys_count": api_keys_count
        })
        
        return HealthResponse(
            status=status,
            service="image-translation-backend",
            version="1.0.0",
            redis_connected=redis_connected,
            gemini_healthy=gemini_healthy,
            api_keys_count=api_keys_count
        )
    
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            service="image-translation-backend",
            version="1.0.0",
            redis_connected=False,
            gemini_healthy=False,
            api_keys_count=0
        )


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics():
    """
    Get basic service metrics
    """
    try:
        # Check Redis connection
        redis_connected = False
        if redis_client.redis:
            try:
                await redis_client.redis.ping()
                redis_connected = True
            except Exception:
                pass
        
        # Get active keys count (keys that are not marked as failed)
        active_keys = 0
        for key_info in api_key_manager.keys:
            if not await api_key_manager.is_key_failed(key_info):
                active_keys += 1
        
        # Get worker pool stats
        worker_stats = await worker_pool.get_stats()
        
        # Get queue stats
        queue_stats = await task_manager.get_queue_stats()
        
        return MetricsResponse(
            status="ok",
            redis_connected=redis_connected,
            active_keys=active_keys,
            total_requests=worker_stats.get("tasks_processed", 0)
        )
    
    except Exception as e:
        logger.error(f"Metrics collection failed: {e}")
        return MetricsResponse(
            status="error",
            redis_connected=False,
            active_keys=0
        )


@router.get("/languages")
async def get_supported_languages():
    """
    Get list of supported translation languages
    """
    languages = []
    for lang in TranslationLanguage:
        languages.append({
            "code": lang.name.lower(),
            "name": lang.value
        })
    
    return {
        "supported_languages": languages,
        "default": TranslationLanguage.VIETNAMESE.value
    }


@router.get("/stats")
async def get_queue_stats():
    """
    Get comprehensive queue and worker statistics
    """
    try:
        # Get queue stats
        queue_stats = await task_manager.get_queue_stats()
        
        # Get worker pool stats
        worker_stats = await worker_pool.get_stats()
        
        # Get active API keys count
        active_keys = 0
        for key_info in api_key_manager.keys:
            if not await api_key_manager.is_key_failed(key_info):
                active_keys += 1
        
        return {
            "queue": queue_stats,
            "workers": worker_stats,
            "api_keys": {
                "total": len(api_key_manager.keys),
                "active": active_keys
            },
            "capacity_estimate": {
                "requests_per_minute": active_keys * 60,  # Rough estimate
                "max_workers": settings.MAX_WORKERS,
                "current_workers": worker_stats.get("total_workers", 0)
            }
        }
    
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return {
            "error": "Failed to get statistics",
            "queue": {"pending": 0, "processing": 0, "total": 0},
            "workers": {"total_workers": 0, "active_workers": 0},
            "api_keys": {"total": 0, "active": 0}
        }