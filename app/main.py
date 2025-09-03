import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from loguru import logger

from .core.config import settings
from .core.logging import setup_logging
from .core.redis_client import redis_client
from .core.genai_client_manager import genai_client_manager
from .services.worker_pool import worker_pool
from .services.task_manager import task_manager
from .middleware.request_id import RequestIDMiddleware
from .middleware.security_headers import SecurityHeadersMiddleware
from .middleware.rate_limiting import RateLimitMiddleware
from .middleware.file_validation import FileValidationMiddleware
from .middleware.timeout import TimeoutMiddleware
from .middleware.logging import LoggingMiddleware
from .middleware.error_handler import ErrorHandlerMiddleware
from .api import translation, monitoring


async def _cleanup_task():
    """Background task to cleanup stale processing tasks"""
    while True:
        try:
            await asyncio.sleep(300)  # Run every 5 minutes
            cleanup_count = await task_manager.cleanup_stale_tasks()
            if cleanup_count > 0:
                logger.info(f"Cleaned up {cleanup_count} stale tasks")
        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure logs directory exists first
    os.makedirs("logs", exist_ok=True)
    
    # Setup logging before any other logger calls
    setup_logging()
    
    # Startup
    logger.info("Starting up Image Translation Backend")
    
    # Connect to Redis
    try:
        await redis_client.connect()
        logger.info("Redis connected successfully")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        # Continue without Redis for development
    
    # Start worker pool
    try:
        await worker_pool.start()
        logger.info("Worker pool started successfully")
    except Exception as e:
        logger.error(f"Failed to start worker pool: {e}")
        
    # Start cleanup task for stale tasks
    asyncio.create_task(_cleanup_task())
        
    logger.info("Application startup complete")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Image Translation Backend")
    
    # Stop worker pool
    try:
        await worker_pool.stop()
        logger.info("Worker pool stopped")
    except Exception as e:
        logger.error(f"Error stopping worker pool: {e}")
    
    # Close GenAI client manager
    try:
        await genai_client_manager.close_all()
        logger.info("GenAI client manager closed")
    except Exception as e:
        logger.error(f"Error closing GenAI client manager: {e}")
    
    # Disconnect Redis
    await redis_client.disconnect()
    logger.info("Application shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="Image Translation Backend",
    description="FastAPI backend service for image translation using Gemini API with intelligent API key rotation and rate limiting",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Add middleware in reverse order of execution
# (Last added is executed first)

# Error handling (outermost)
app.add_middleware(ErrorHandlerMiddleware)

# Logging
app.add_middleware(LoggingMiddleware)

# Timeout handling
app.add_middleware(TimeoutMiddleware)

# File validation
app.add_middleware(FileValidationMiddleware)

# Rate limiting
app.add_middleware(RateLimitMiddleware)

# CORS (should be after rate limiting)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Security headers
app.add_middleware(SecurityHeadersMiddleware)

# Request ID generation
app.add_middleware(RequestIDMiddleware)

# Gzip compression (innermost, closest to application)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Include API routes
app.include_router(translation.router, prefix="/api/v1")
app.include_router(monitoring.router)

# Shared dependency for service status checks
async def get_service_status():
    """
    Shared dependency to check service status (Redis, Gemini, API keys)
    """
    from .services.gemini_service import gemini_service
    from .services.key_rotation import api_key_manager
    
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
    
    # Get active keys count (keys that are not marked as failed)
    active_keys = 0
    total_keys = len(api_key_manager.keys)
    
    for key_info in api_key_manager.keys:
        if not await api_key_manager.is_key_failed(key_info):
            active_keys += 1
    
    return {
        "redis_connected": redis_connected,
        "gemini_healthy": gemini_healthy,
        "gemini_status": gemini_status,
        "active_keys": active_keys,
        "total_keys": total_keys
    }




if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=True,
        log_level=settings.LOG_LEVEL.lower()
    )