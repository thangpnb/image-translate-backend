import asyncio
import time
import random
from typing import List, Dict, Optional, Tuple, Set
from loguru import logger
from ..core.config import settings
from ..core.redis_client import redis_client


class APIKeyManager:
    def __init__(self):
        self.keys: List[Dict] = []
        self.key_count = 0
        self.failed_keys: Set[str] = set()
        self.key_scores: Dict[str, float] = {}  # Dynamic scoring for keys
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
        """Get next available API key using intelligent rotation with scoring"""
        if self.key_count == 0:
            logger.error("No API keys available")
            return None
        
        # Update key health status and check for recovered keys
        await self._update_key_health()
        
        # Get available keys (not disabled) sorted by score (best first)
        available_keys = await self._get_available_keys()
        
        if not available_keys:
            logger.warning("All API keys are unavailable or disabled")
            return None
        
        # Select key using weighted random selection
        selected_key = self._weighted_key_selection(available_keys)
        return selected_key["api_key"], selected_key
    
    async def _update_key_health(self):
        """Update the health status of all keys and check for recovered keys"""
        try:
            # Check for recovered keys from failure list
            recovered_keys = []
            for key_id in self.failed_keys.copy():
                if not await self._is_key_in_failure_state(key_id):
                    recovered_keys.append(key_id)
                    self.failed_keys.discard(key_id)
            
            if recovered_keys:
                logger.info(f"Keys recovered from failure: {recovered_keys}")
            
            # Check for keys that should be re-enabled after rate limit recovery
            await self._check_and_enable_recovered_keys()
                
        except Exception as e:
            logger.error(f"Error updating key health: {e}")
    
    async def _get_available_keys(self) -> List[Dict]:
        """Get available keys (not disabled) with health scores"""
        available_keys = []
        
        for key_info in self.keys:
            key_id = key_info["id"]
            
            # Skip failed keys
            if key_id in self.failed_keys:
                continue
                
            # Skip disabled keys (reactive rate limiting)
            if await self._is_key_disabled(key_id):
                continue
                
            score = await self._calculate_key_score(key_info)
            key_info_with_score = {**key_info, "score": score}
            available_keys.append(key_info_with_score)
        
        # Sort by score (higher is better)
        available_keys.sort(key=lambda k: k["score"], reverse=True)
        return available_keys
    
    def _weighted_key_selection(self, keys: List[Dict]) -> Dict:
        """Select key using weighted random based on scores"""
        if not keys:
            return None
            
        # Use top 3 keys for weighted selection to balance load
        top_keys = keys[:min(3, len(keys))]
        
        if len(top_keys) == 1:
            return top_keys[0]
        
        # Weight based on scores with some randomness
        weights = [key["score"] + random.uniform(0.1, 0.3) for key in top_keys]
        selected = random.choices(top_keys, weights=weights, k=1)[0]
        
        logger.debug(f"Selected key {selected['id']} with score {selected['score']:.2f}")
        return selected
    
    async def _is_key_disabled(self, key_id: str) -> bool:
        """Check if key is disabled due to rate limits"""
        try:
            current_time = int(time.time())
            
            # Check if key is disabled for any rate limit type
            disable_keys = [
                f"key_disabled_until:{key_id}:RPM",
                f"key_disabled_until:{key_id}:RPD", 
                f"key_disabled_until:{key_id}:TPM"
            ]
            
            values = await redis_client.mget(*disable_keys)
            
            for disable_until_str in values:
                if disable_until_str:
                    disable_until = int(disable_until_str)
                    if current_time < disable_until:
                        return True  # Key is still disabled
            
            return False  # Key is not disabled
            
        except Exception as e:
            logger.error(f"Error checking key disabled state for {key_id}: {e}")
            return False  # Don't disable on error
    
    async def _disable_key_for_limit(self, key_id: str, limit_type: str, disable_until: int):
        """Disable key for specific limit type until specified time"""
        try:
            disable_key = f"key_disabled_until:{key_id}:{limit_type}"
            expire_seconds = disable_until - int(time.time())
            
            if expire_seconds > 0:
                await redis_client.set(disable_key, str(disable_until), expire=expire_seconds)
                logger.info(f"Key {key_id} disabled for {limit_type} until {disable_until} ({expire_seconds}s)")
            
        except Exception as e:
            logger.error(f"Error disabling key {key_id} for {limit_type}: {e}")
    
    async def _check_and_enable_recovered_keys(self):
        """Check and enable keys that have passed their disable time"""
        try:
            current_time = int(time.time())
            recovered_count = 0
            
            for key_info in self.keys:
                key_id = key_info["id"]
                
                # Check each limit type
                for limit_type in ["RPM", "RPD", "TPM"]:
                    disable_key = f"key_disabled_until:{key_id}:{limit_type}"
                    disable_until_str = await redis_client.get(disable_key)
                    
                    if disable_until_str:
                        disable_until = int(disable_until_str)
                        if current_time >= disable_until:
                            await redis_client.delete(disable_key)
                            logger.info(f"Key {key_id} recovered from {limit_type} limit")
                            recovered_count += 1
            
            if recovered_count > 0:
                logger.info(f"Total {recovered_count} key-limit pairs recovered")
                
        except Exception as e:
            logger.error(f"Error checking recovered keys: {e}")

    
    async def record_key_usage(self, key_info: Dict, tokens_used: int = 0) -> bool:
        """Record API key usage and check for rate limit violations (reactive approach)
        Returns False if key was disabled due to rate limits"""
        key_id = key_info["id"]
        
        current_minute = int(time.time()) // 60
        current_day = int(time.time()) // (24 * 3600)
        current_time = int(time.time())
        
        try:
            # Batch increment all counters
            pipeline_ops = [
                (f"key_rpm:{key_id}:{current_minute}", 1, 60),
                (f"key_rpd:{key_id}:{current_day}", 1, 86400)
            ]
            
            if tokens_used > 0:
                pipeline_ops.append((f"key_tpm:{key_id}:{current_minute}", tokens_used, 60))
            
            # Execute all increments in pipeline for better performance
            for key, increment, expire in pipeline_ops:
                await redis_client.incrby(key, increment)
                await redis_client.expire(key, expire)
            
            # Get new counts after increment for reactive rate limiting
            keys_to_check = [
                f"key_rpm:{key_id}:{current_minute}",
                f"key_rpd:{key_id}:{current_day}", 
                f"key_tpm:{key_id}:{current_minute}"
            ]
            
            values = await redis_client.mget(*keys_to_check)
            rpm_count, rpd_count, tpm_count = [int(v) if v else 0 for v in values]
            
            # Check against rate limits and disable if exceeded (reactive approach)
            rpm_limit = settings.DEFAULT_RPM
            rpd_limit = settings.DEFAULT_RPD
            tpm_limit = settings.DEFAULT_TPM
            
            key_disabled = False
            
            if rpm_count >= rpm_limit:
                await self._disable_key_for_limit(key_id, "RPM", current_time + 60)  # Disable until next minute
                logger.warning(f"Key {key_id} disabled due to RPM limit: {rpm_count}/{rpm_limit}")
                key_disabled = True
                
            if rpd_count >= rpd_limit:
                next_day = (current_day + 1) * 86400  # Next day start
                await self._disable_key_for_limit(key_id, "RPD", next_day)
                logger.warning(f"Key {key_id} disabled due to RPD limit: {rpd_count}/{rpd_limit}")
                key_disabled = True
                
            if tokens_used > 0 and tpm_count >= tpm_limit:
                await self._disable_key_for_limit(key_id, "TPM", current_time + 60)  # Disable until next minute
                logger.warning(f"Key {key_id} disabled due to TPM limit: {tpm_count}/{tpm_limit}")
                key_disabled = True
            
            # Update success metrics for scoring
            await self._update_success_metrics(key_id)
            
            logger.debug(f"Recorded usage for key {key_id}: tokens={tokens_used}, disabled={key_disabled}")
            
            return not key_disabled  # Return True if key is still available
            
        except Exception as e:
            logger.error(f"Error recording key usage for {key_id}: {e}")
            await self._update_error_metrics(key_id)
            return True  # Don't disable on error
    
    async def mark_key_failed(self, key_info: Dict, failure_duration: int = 300):
        """Mark key as failed with exponential backoff"""
        key_id = key_info["id"]
        
        try:
            # Add to internal failed set
            self.failed_keys.add(key_id)
            
            # Get current failure count for exponential backoff
            failure_count_key = f"key_failures:{key_id}"
            current_failures = await redis_client.get(failure_count_key)
            failure_count = int(current_failures) if current_failures else 0
            failure_count += 1
            
            # Exponential backoff: 5min, 15min, 45min, max 2 hours
            backoff_duration = min(failure_duration * (3 ** (failure_count - 1)), 7200)
            
            failure_key = f"key_failed:{key_id}"
            await redis_client.set(failure_key, str(failure_count), expire=backoff_duration)
            await redis_client.set(failure_count_key, str(failure_count), expire=86400)  # Track for 24h
            
            # Update error metrics
            await self._update_error_metrics(key_id)
            
            logger.warning(f"Key {key_id} failed (attempt #{failure_count}), backoff: {backoff_duration}s")
            
        except Exception as e:
            logger.error(f"Error marking key as failed for {key_id}: {e}")
    
    async def is_key_failed(self, key_info: Dict) -> bool:
        """Check if key is marked as failed"""
        key_id = key_info["id"]
        return key_id in self.failed_keys
    
    async def _is_key_in_failure_state(self, key_id: str) -> bool:
        """Check if key is still in Redis failure state"""
        try:
            failure_key = f"key_failed:{key_id}"
            return await redis_client.exists(failure_key)
        except Exception as e:
            logger.error(f"Error checking key failure state for {key_id}: {e}")
            return False
    
    async def _calculate_key_score(self, key_info: Dict) -> float:
        """Calculate dynamic score for key selection based on performance metrics using global rate limits"""
        key_id = key_info["id"]
        
        try:
            current_minute = int(time.time()) // 60
            current_day = int(time.time()) // (24 * 3600)
            
            # Get current usage
            usage_keys = [
                f"key_rpm:{key_id}:{current_minute}",
                f"key_rpd:{key_id}:{current_day}",
                f"key_tpm:{key_id}:{current_minute}",
                f"key_success:{key_id}",
                f"key_errors:{key_id}"
            ]
            
            values = await redis_client.mget(*usage_keys)
            rpm_used, rpd_used, tpm_used, success_count, error_count = [
                int(v) if v else 0 for v in values
            ]
            
            # Calculate capacity remaining using global rate limits from .env
            rpm_limit = settings.DEFAULT_RPM
            rpd_limit = settings.DEFAULT_RPD  
            tpm_limit = settings.DEFAULT_TPM
            
            rpm_capacity = max(0, (rpm_limit - rpm_used) / rpm_limit)
            rpd_capacity = max(0, (rpd_limit - rpd_used) / rpd_limit)
            tmp_capacity = max(0, (tpm_limit - tpm_used) / tpm_limit)
            
            # Performance metrics (success rate, error rate)
            total_requests = success_count + error_count
            success_rate = success_count / max(total_requests, 1)
            error_penalty = error_count / max(total_requests + 10, 10)  # Small denominator boost
            
            # Weighted scoring
            capacity_score = (rpm_capacity * 0.4 + rpd_capacity * 0.2 + tmp_capacity * 0.4)
            performance_score = success_rate * 0.7 - error_penalty * 0.3
            
            final_score = capacity_score * 0.6 + performance_score * 0.4
            
            return min(max(final_score, 0.0), 1.0)  # Clamp between 0-1
            
        except Exception as e:
            logger.error(f"Error calculating score for key {key_id}: {e}")
            return 0.5  # Default middle score
    
    async def _update_success_metrics(self, key_id: str):
        """Update success metrics for key scoring"""
        try:
            success_key = f"key_success:{key_id}"
            await redis_client.incr(success_key)
            await redis_client.expire(success_key, 86400)  # 24 hour rolling
        except Exception as e:
            logger.error(f"Error updating success metrics for {key_id}: {e}")
    
    async def _update_error_metrics(self, key_id: str):
        """Update error metrics for key scoring"""
        try:
            error_key = f"key_errors:{key_id}"
            await redis_client.incr(error_key)
            await redis_client.expire(error_key, 86400)  # 24 hour rolling
        except Exception as e:
            logger.error(f"Error updating error metrics for {key_id}: {e}")
    
    async def get_key_stats(self) -> Dict:
        """Get comprehensive stats for all keys for monitoring"""
        stats = {
            "total_keys": self.key_count,
            "failed_keys": len(self.failed_keys),
            "key_details": []
        }
        
        try:
            for key_info in self.keys:
                key_id = key_info["id"]
                score = await self._calculate_key_score(key_info)
                is_disabled = await self._is_key_disabled(key_id)
                is_failed = key_id in self.failed_keys
                
                key_stats = {
                    "id": key_id,
                    "score": round(score, 3),
                    "available": not is_disabled and not is_failed,
                    "disabled": is_disabled,
                    "failed": is_failed
                }
                stats["key_details"].append(key_stats)
                
            return stats
            
        except Exception as e:
            logger.error(f"Error getting key stats: {e}")
            return stats


# Global API key manager instance
api_key_manager = APIKeyManager()