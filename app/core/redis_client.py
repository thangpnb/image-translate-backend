import redis.asyncio as redis
from typing import Optional
from loguru import logger
from .config import settings


class RedisClient:
    def __init__(self):
        self.redis: Optional[redis.Redis] = None
        
    async def connect(self):
        """Initialize Redis connection"""
        try:
            self.redis = redis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=200,
                retry_on_timeout=True
            )
            
            # Test connection
            await self.redis.ping()
            logger.info("Redis connection established successfully")
            
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    async def disconnect(self):
        """Close Redis connection"""
        if self.redis:
            await self.redis.close()
            logger.info("Redis connection closed")
    
    async def get(self, key: str) -> Optional[str]:
        """Get value from Redis"""
        try:
            return await self.redis.get(key)
        except Exception as e:
            logger.error(f"Redis GET error for key {key}: {e}")
            return None
    
    async def set(self, key: str, value: str, expire: Optional[int] = None) -> bool:
        """Set value in Redis with optional expiration"""
        try:
            return await self.redis.set(key, value, ex=expire)
        except Exception as e:
            logger.error(f"Redis SET error for key {key}: {e}")
            return False
    
    async def incr(self, key: str, expire: Optional[int] = None) -> int:
        """Increment counter atomically"""
        try:
            value = await self.redis.incr(key)
            if expire and value == 1:  # Set expiration only on first increment
                await self.redis.expire(key, expire)
            return value
        except Exception as e:
            logger.error(f"Redis INCR error for key {key}: {e}")
            return 0
    
    async def exists(self, key: str) -> bool:
        """Check if key exists"""
        try:
            return bool(await self.redis.exists(key))
        except Exception as e:
            logger.error(f"Redis EXISTS error for key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key from Redis"""
        try:
            return bool(await self.redis.delete(key))
        except Exception as e:
            logger.error(f"Redis DELETE error for key {key}: {e}")
            return False
    
    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiration for key"""
        try:
            return await self.redis.expire(key, seconds)
        except Exception as e:
            logger.error(f"Redis EXPIRE error for key {key}: {e}")
            return False
    
    async def mget(self, *keys: str) -> list:
        """Get multiple values at once"""
        try:
            return await self.redis.mget(*keys)
        except Exception as e:
            logger.error(f"Redis MGET error for keys {keys}: {e}")
            return [None] * len(keys)
    
    async def incrby(self, key: str, amount: int = 1) -> int:
        """Increment by specific amount"""
        try:
            return await self.redis.incrby(key, amount)
        except Exception as e:
            logger.error(f"Redis INCRBY error for key {key}: {e}")
            return 0
    
    async def lpush(self, key: str, *values) -> int:
        """Push values to left side of list"""
        try:
            return await self.redis.lpush(key, *values)
        except Exception as e:
            logger.error(f"Redis LPUSH error for key {key}: {e}")
            return 0
    
    async def rpop(self, key: str) -> Optional[str]:
        """Pop value from right side of list"""
        try:
            return await self.redis.rpop(key)
        except Exception as e:
            logger.error(f"Redis RPOP error for key {key}: {e}")
            return None
    
    async def llen(self, key: str) -> int:
        """Get length of list"""
        try:
            return await self.redis.llen(key)
        except Exception as e:
            logger.error(f"Redis LLEN error for key {key}: {e}")
            return 0
    
    async def sadd(self, key: str, *values) -> int:
        """Add values to set"""
        try:
            return await self.redis.sadd(key, *values)
        except Exception as e:
            logger.error(f"Redis SADD error for key {key}: {e}")
            return 0
    
    async def srem(self, key: str, *values) -> int:
        """Remove values from set"""
        try:
            return await self.redis.srem(key, *values)
        except Exception as e:
            logger.error(f"Redis SREM error for key {key}: {e}")
            return 0
    
    async def scard(self, key: str) -> int:
        """Get cardinality (size) of set"""
        try:
            return await self.redis.scard(key)
        except Exception as e:
            logger.error(f"Redis SCARD error for key {key}: {e}")
            return 0
    
    async def smembers(self, key: str) -> set:
        """Get all members of set"""
        try:
            return await self.redis.smembers(key)
        except Exception as e:
            logger.error(f"Redis SMEMBERS error for key {key}: {e}")
            return set()


# Global Redis client instance
redis_client = RedisClient()