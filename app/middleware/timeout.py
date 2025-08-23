import asyncio
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from loguru import logger
from ..core.config import settings


class TimeoutMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            # Set timeout for request processing
            response = await asyncio.wait_for(
                call_next(request),
                timeout=settings.REQUEST_TIMEOUT
            )
            return response
            
        except asyncio.TimeoutError:
            logger.error(f"Request timeout for {request.url.path}")
            raise HTTPException(
                status_code=504,
                detail="Request timeout. Please try again with a smaller file or check your connection."
            )
        except Exception as e:
            logger.error(f"Request processing error: {e}")
            raise