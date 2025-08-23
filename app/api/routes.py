import time
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import JSONResponse
import magic
from loguru import logger
from ..models.schemas import (
    TranslationResponse, 
    ErrorResponse, 
    HealthResponse, 
    MetricsResponse,
    TranslationLanguage
)
from ..services.gemini_service import gemini_service
from ..services.key_rotation import api_key_manager
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


@router.post("/translate", response_model=TranslationResponse)
async def translate_image(
    request: Request,
    file: UploadFile = File(..., description="Image file to translate"),
    target_language: TranslationLanguage = Form(
        default=TranslationLanguage.VIETNAMESE,
        description="Target language for translation"
    )
):
    """
    Translate text in uploaded image to target language
    """
    start_time = time.time()
    request_id = getattr(request.state, 'request_id', 'unknown')
    
    logger.info(f"Translation request received", extra={
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
        
        # Perform translation
        success, result, error = await gemini_service.translate_image(
            file_content, 
            target_language.value
        )
        
        processing_time = time.time() - start_time
        
        if success:
            logger.info(f"Translation completed successfully", extra={
                "request_id": request_id,
                "processing_time": processing_time,
                "result_length": len(result)
            })
            
            return TranslationResponse(
                success=True,
                translated_text=result,
                target_language=target_language.value,
                request_id=request_id,
                processing_time=round(processing_time, 3)
            )
        else:
            logger.error(f"Translation failed: {error}", extra={"request_id": request_id})
            
            return TranslationResponse(
                success=False,
                translated_text=None,
                target_language=target_language.value,
                request_id=request_id,
                processing_time=round(processing_time, 3),
                error=error
            )
    
    except HTTPException:
        raise
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"Unexpected error in translation: {e}", extra={
            "request_id": request_id,
            "processing_time": processing_time
        })
        
        return TranslationResponse(
            success=False,
            translated_text=None,
            target_language=target_language.value,
            request_id=request_id,
            processing_time=round(processing_time, 3),
            error="Internal server error"
        )


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
        
        return MetricsResponse(
            status="ok",
            redis_connected=redis_connected,
            active_keys=active_keys
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