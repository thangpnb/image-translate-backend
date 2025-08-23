import magic
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from loguru import logger
from ..core.config import settings


class FileValidationMiddleware(BaseHTTPMiddleware):
    ALLOWED_MIME_TYPES = {
        'image/jpeg',
        'image/png',
        'image/gif',
        'image/webp',
        'image/bmp',
        'image/tiff'
    }
    
    async def dispatch(self, request: Request, call_next):
        # Only validate file uploads
        if request.method == "POST" and "multipart/form-data" in request.headers.get("content-type", ""):
            await self.validate_file_upload(request)
        
        return await call_next(request)
    
    async def validate_file_upload(self, request: Request):
        """Validate file size and type before processing"""
        content_length = request.headers.get("content-length")
        
        # Check content length
        if content_length:
            size = int(content_length)
            if size > settings.MAX_UPLOAD_SIZE:
                logger.warning(f"File too large: {size} bytes")
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large. Maximum size allowed: {settings.MAX_UPLOAD_SIZE} bytes"
                )
        
        # Note: Content type validation will be done in the route handler
        # where we have access to the actual file content