from fastapi import APIRouter
from loguru import logger

from ..models.schemas import MetricsResponse
from ..services.gemini_service import gemini_service
from ..services.key_rotation import api_key_manager
from ..services.worker_pool import worker_pool
from ..services.task_manager import task_manager
from ..core.redis_client import redis_client
from ..core.config import settings

router = APIRouter(tags=["Monitoring"])


@router.get("/health")
async def health_check():
    """
    Comprehensive health check endpoint
    """
    try:
        print("=== HEALTH CHECK STARTING ===")
        logger.info("Starting health check")
        
        # Check Redis connection
        redis_connected = False
        if redis_client.redis:
            try:
                await redis_client.redis.ping()
                redis_connected = True
                logger.info("Redis connection: OK")
                print("Redis: OK")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}")
                print(f"Redis failed: {e}")
        else:
            logger.warning("Redis client not initialized")
            print("Redis client not initialized")
        
        # Check Gemini service
        logger.info("Checking Gemini service...")
        print("Checking Gemini...")
        gemini_healthy, gemini_status = await gemini_service.health_check()
        logger.info(f"Gemini service: {gemini_healthy}, status: {gemini_status}")
        print(f"Gemini: {gemini_healthy}, {gemini_status}")
        
        # Get API keys count
        api_keys_count = len(api_key_manager.keys)
        logger.info(f"API keys count: {api_keys_count}")
        print(f"API keys: {api_keys_count}")
        
        status = "healthy"
        if not redis_connected:
            status = "degraded"
        if not gemini_healthy:
            status = "unhealthy"
        if api_keys_count == 0:
            status = "unhealthy"
        
        logger.info(f"Health check completed: {status}", extra={
            "redis_connected": redis_connected,
            "gemini_healthy": gemini_healthy,
            "api_keys_count": api_keys_count
        })
        
        result = {
            "status": status,
            "service": "image-translation-backend",
            "version": "1.0.0",
            "redis_connected": redis_connected,
            "gemini_healthy": gemini_healthy,
            "api_keys_count": api_keys_count
        }
        print(f"Returning: {result}")
        return result
    
    except Exception as e:
        print(f"=== HEALTH CHECK EXCEPTION: {e} ===")
        logger.error(f"Health check failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "status": "unhealthy",
            "service": "image-translation-backend",
            "version": "1.0.0",
            "redis_connected": False,
            "gemini_healthy": False,
            "api_keys_count": 0
        }


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