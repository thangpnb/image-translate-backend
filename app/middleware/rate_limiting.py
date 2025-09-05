import time
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from loguru import logger
from ..core.redis_client import redis_client
from ..core.config import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Get client IP
        client_ip = self.get_client_ip(request)
        
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/metrics"]:
            return await call_next(request)
        
        # Check rate limit
        if not await self.check_rate_limit(client_ip):
            logger.warning(f"Rate limit exceeded for IP: {client_ip}")
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again later.",
                headers={"Retry-After": "60"}
            )
        
        return await call_next(request)
    
    def get_client_ip(self, request: Request) -> str:
        """Extract client IP from request"""
        # Check for forwarded headers (behind proxy)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fallback to direct connection
        return request.client.host if request.client else "unknown"
    
    async def check_rate_limit(self, client_ip: str) -> bool:
        """Check if client IP is within rate limits"""
        try:
            current_minute = int(time.time()) // 60
            key = f"rate_limit:{client_ip}:{current_minute}"
            
            # Increment counter for current minute
            count = await redis_client.incr(key, expire=settings.REDIS_RATE_LIMIT_EXPIRE)
            
            # Check against limits
            if count > settings.GLOBAL_RATE_LIMIT:
                return False
            
            # Check burst limit (last 10 seconds)
            current_10s = int(time.time()) // 10
            burst_key = f"burst_limit:{client_ip}:{current_10s}"
            burst_count = await redis_client.incr(burst_key, expire=settings.REDIS_BURST_LIMIT_EXPIRE)
            
            if burst_count > settings.BURST_RATE_LIMIT:
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Rate limiting check failed: {e}")
            # Allow request if Redis is down
            return True