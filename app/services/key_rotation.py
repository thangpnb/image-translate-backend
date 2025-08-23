import asyncio
import time
from typing import List, Dict, Optional, Tuple
from loguru import logger
from ..core.config import settings
from ..core.redis_client import redis_client


class APIKeyManager:
    def __init__(self):
        self.keys: List[Dict] = []
        self.key_count = 0
        self.load_keys()
    
    def load_keys(self):
        """Load API keys from configuration"""
        key_data = settings.load_api_keys()
        self.keys = key_data.get("keys", [])
        self.key_count = len(self.keys)
        
        if self.key_count == 0:
            logger.warning("No API keys loaded from configuration")
        else:
            logger.info(f"Loaded {self.key_count} API keys")
    
    async def get_available_key(self) -> Optional[Tuple[str, Dict]]:
        """Get next available API key using smart rotation"""
        if self.key_count == 0:
            logger.error("No API keys available")
            return None
        
        # Try each key in rotation
        for attempt in range(self.key_count):
            key_info = await self._get_next_key()
            if key_info and await self._check_key_limits(key_info):
                return key_info["api_key"], key_info
        
        logger.warning("All API keys have reached their limits")
        return None
    
    async def _get_next_key(self) -> Optional[Dict]:
        """Get next key using atomic Redis counter"""
        try:
            # Use Redis counter for atomic key selection
            counter = await redis_client.incr("api_key_counter")
            key_index = (counter - 1) % self.key_count
            
            return self.keys[key_index]
            
        except Exception as e:
            logger.error(f"Error getting next key: {e}")
            # Fallback to first key if Redis is unavailable
            return self.keys[0] if self.keys else None
    
    async def _check_key_limits(self, key_info: Dict) -> bool:
        """Check if key is within rate limits"""
        key_id = key_info["id"]
        limits = key_info.get("limits", {})
        
        current_minute = int(time.time()) // 60
        current_day = int(time.time()) // (24 * 3600)
        
        try:
            # Check requests per minute
            rpm_limit = limits.get("requests_per_minute", settings.DEFAULT_RPM)
            rpm_key = f"key_rpm:{key_id}:{current_minute}"
            rpm_count = await redis_client.get(rpm_key)
            
            if rpm_count and int(rpm_count) >= rpm_limit:
                logger.debug(f"Key {key_id} exceeded RPM limit: {rpm_count}/{rpm_limit}")
                return False
            
            # Check requests per day
            rpd_limit = limits.get("requests_per_day", settings.DEFAULT_RPD)
            rpd_key = f"key_rpd:{key_id}:{current_day}"
            rpd_count = await redis_client.get(rpd_key)
            
            if rpd_count and int(rpd_count) >= rpd_limit:
                logger.debug(f"Key {key_id} exceeded RPD limit: {rpd_count}/{rpd_limit}")
                return False
            
            # Check tokens per minute (estimated)
            tpm_limit = limits.get("tokens_per_minute", settings.DEFAULT_TPM)
            tpm_key = f"key_tpm:{key_id}:{current_minute}"
            tpm_count = await redis_client.get(tpm_key)
            
            if tpm_count and int(tpm_count) >= tpm_limit:
                logger.debug(f"Key {key_id} exceeded TPM limit: {tpm_count}/{tpm_limit}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking key limits for {key_id}: {e}")
            # Allow usage if Redis check fails
            return True
    
    async def record_key_usage(self, key_info: Dict, tokens_used: int = 0):
        """Record API key usage for rate limiting"""
        key_id = key_info["id"]
        
        current_minute = int(time.time()) // 60
        current_day = int(time.time()) // (24 * 3600)
        
        try:
            # Increment request counters
            rpm_key = f"key_rpm:{key_id}:{current_minute}"
            rpd_key = f"key_rpd:{key_id}:{current_day}"
            
            await redis_client.incr(rpm_key, expire=60)  # Expire after 1 minute
            await redis_client.incr(rpd_key, expire=86400)  # Expire after 1 day
            
            # Record token usage if provided
            if tokens_used > 0:
                tpm_key = f"key_tpm:{key_id}:{current_minute}"
                await redis_client.incr(tpm_key, expire=60)
                
                # Add the actual token count to the counter
                current_tokens = await redis_client.get(tpm_key)
                if current_tokens:
                    new_count = int(current_tokens) + tokens_used - 1  # -1 because we already incremented
                    await redis_client.set(tpm_key, str(new_count), expire=60)
            
            logger.debug(f"Recorded usage for key {key_id}: tokens={tokens_used}")
            
        except Exception as e:
            logger.error(f"Error recording key usage for {key_id}: {e}")
    
    async def mark_key_failed(self, key_info: Dict, failure_duration: int = 300):
        """Mark key as temporarily failed"""
        key_id = key_info["id"]
        
        try:
            failure_key = f"key_failed:{key_id}"
            await redis_client.set(failure_key, "1", expire=failure_duration)
            logger.warning(f"Marked key {key_id} as failed for {failure_duration} seconds")
            
        except Exception as e:
            logger.error(f"Error marking key as failed for {key_id}: {e}")
    
    async def is_key_failed(self, key_info: Dict) -> bool:
        """Check if key is marked as failed"""
        key_id = key_info["id"]
        
        try:
            failure_key = f"key_failed:{key_id}"
            return await redis_client.exists(failure_key)
            
        except Exception as e:
            logger.error(f"Error checking key failure status for {key_id}: {e}")
            return False


# Global API key manager instance
api_key_manager = APIKeyManager()