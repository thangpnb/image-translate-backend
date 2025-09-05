import asyncio
import uuid
import base64
import socket
from datetime import datetime, timezone
from typing import Dict, Optional, Set, List
from loguru import logger
from ..core.config import settings
from ..core.redis_client import redis_client
from ..services.task_manager import task_manager
from ..services.gemini_service import gemini_service
from ..services.key_rotation import api_key_manager
from ..models.schemas import TaskStatus, TranslationLanguage


class TranslationWorker:
    def __init__(self, worker_id: str, worker_pool: 'DistributedWorkerPool'):
        self.worker_id = worker_id
        self.worker_pool = worker_pool
        self.is_running = False
        self.current_task_id: Optional[str] = None
        self.last_activity = datetime.now(timezone.utc)
        self.processed_tasks = 0
        self.successful_tasks = 0
        self.failed_tasks = 0
        
    async def start(self):
        """Start the worker"""
        self.is_running = True
        logger.info(f"Worker {self.worker_id} started")
        
        while self.is_running:
            try:
                # Get next task from queue
                task_id = await task_manager.get_next_task(self.worker_id)
                
                if not task_id:
                    # No tasks available, wait a bit
                    await asyncio.sleep(0.5)
                    continue
                
                self.current_task_id = task_id
                self.last_activity = datetime.now(timezone.utc)
                
                # Process the task
                await self._process_task(task_id)
                
                self.current_task_id = None
                self.processed_tasks += 1
                
            except Exception as e:
                logger.error(f"Worker {self.worker_id} error: {e}")
                if self.current_task_id:
                    await task_manager.fail_task(self.current_task_id, str(e))
                    self.current_task_id = None
                await asyncio.sleep(1)  # Wait before retrying
        
        logger.info(f"Worker {self.worker_id} stopped")
    
    async def _process_task(self, task_id: str):
        """Process a translation task (supports multiple images)"""
        start_time = datetime.now(timezone.utc)
        
        try:
            # Get task details
            task = await task_manager.get_task(task_id)
            if not task:
                await task_manager.fail_task(task_id, "Task not found")
                self.failed_tasks += 1
                return
            
            # Handle both single and multiple images
            images_to_process = []
            if task.images_data:  # New multiple images format
                images_to_process = task.images_data
            elif task.image_data:  # Backward compatibility
                images_to_process = [task.image_data]
            else:
                await task_manager.fail_task(task_id, "No image data found")
                self.failed_tasks += 1
                return
            
            logger.info(f"Worker {self.worker_id} processing task {task_id} with {len(images_to_process)} images in parallel")
            
            # Process all images in parallel using asyncio.gather
            async def process_single_image(index: int, image_data_b64: str):
                """Process a single image and update its result"""
                try:
                    # Decode image data
                    try:
                        image_data = base64.b64decode(image_data_b64)
                    except Exception as e:
                        error_msg = f"Failed to decode image {index + 1} data: {e}"
                        await task_manager.update_partial_result(task_id, index, error=error_msg)
                        return {'success': False, 'error': error_msg}
                    
                    # Convert string to enum for API consistency
                    try:
                        target_lang_enum = TranslationLanguage(task.target_language)
                    except ValueError:
                        # Fallback to Vietnamese if invalid language
                        target_lang_enum = TranslationLanguage.VIETNAMESE
                        logger.warning(f"Unknown target language '{task.target_language}', using Vietnamese fallback")
                    
                    # Perform translation for this image
                    success, result, error = await gemini_service.translate_image(
                        image_data, 
                        target_lang_enum
                    )
                    
                    # Update partial result immediately
                    if success:
                        await task_manager.update_partial_result(task_id, index, result=result)
                        logger.info(f"Worker {self.worker_id} completed image {index + 1}/{len(images_to_process)} in task {task_id}")
                        return {'success': True, 'result': result}
                    else:
                        await task_manager.update_partial_result(task_id, index, error=error or "Translation failed")
                        logger.warning(f"Worker {self.worker_id} failed image {index + 1} in task {task_id}: {error}")
                        return {'success': False, 'error': error or "Translation failed"}
                        
                except Exception as e:
                    error_msg = f"Exception processing image {index + 1}: {str(e)}"
                    await task_manager.update_partial_result(task_id, index, error=error_msg)
                    logger.error(f"Worker {self.worker_id} exception processing image {index + 1} in task {task_id}: {e}")
                    return {'success': False, 'error': error_msg}
            
            # Create tasks for all images and process them in parallel
            image_tasks = [
                process_single_image(index, image_data_b64) 
                for index, image_data_b64 in enumerate(images_to_process)
            ]
            
            # Wait for all images to complete processing
            results = await asyncio.gather(*image_tasks, return_exceptions=True)
            
            # Count successful and failed images
            successful_images = 0
            failed_images = 0
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    # Handle any exceptions from asyncio.gather
                    error_msg = f"Async exception processing image {i + 1}: {str(result)}"
                    await task_manager.update_partial_result(task_id, i, error=error_msg)
                    failed_images += 1
                    logger.error(f"Worker {self.worker_id} async exception for image {i + 1}: {result}")
                elif result.get('success', False):
                    successful_images += 1
                else:
                    failed_images += 1
            
            # Update worker stats
            if successful_images > 0:
                self.successful_tasks += 1
            if failed_images == len(images_to_process):
                self.failed_tasks += 1
            
            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.info(f"Worker {self.worker_id} completed task {task_id} in {processing_time:.2f}s - {successful_images} successful, {failed_images} failed (parallel processing)")
                
        except Exception as e:
            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            # For multiple images, we need to update the task status differently
            task = await task_manager.get_task(task_id)
            if task and task.images_data:
                # Mark all images as failed
                for index in range(len(task.images_data)):
                    await task_manager.update_partial_result(task_id, index, error=str(e))
            else:
                await task_manager.fail_task(task_id, str(e), processing_time)
            
            self.failed_tasks += 1
            logger.error(f"Worker {self.worker_id} exception processing task {task_id}: {e}")
    
    async def stop(self):
        """Stop the worker gracefully"""
        self.is_running = False
        logger.info(f"Worker {self.worker_id} stopping...")


class DistributedWorkerPool:
    def __init__(self):
        self.min_workers = settings.MIN_WORKERS
        self.max_workers = settings.MAX_WORKERS
        self.workers: Dict[str, TranslationWorker] = {}
        self.worker_tasks: Dict[str, asyncio.Task] = {}
        self.is_running = False
        self.scaling_lock = asyncio.Lock()
        self.last_scale_check = datetime.now(timezone.utc)
        self.scale_check_interval = settings.WORKER_SCALE_CHECK_INTERVAL
        
        # Distributed coordination
        self.instance_id = f"instance-{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        self.last_heartbeat = datetime.now(timezone.utc)
        self.heartbeat_interval = 30  # seconds
        
        # Local tracking for performance (still used for local decisions)
        self.completion_history: List[int] = []  # Track completed tasks per minute
        self.scale_history: List[Dict] = []  # Track recent scaling decisions
        
    async def start(self):
        """Start the distributed worker pool"""
        self.is_running = True
        
        # Register this instance in the cluster
        await self._register_instance()
        
        # Start initial workers
        await self._scale_to_workers(self.min_workers)
        
        # Start background tasks
        asyncio.create_task(self._scaling_loop())
        asyncio.create_task(self._heartbeat_loop())
        asyncio.create_task(self._cleanup_stale_instances())
        
        logger.info(f"Distributed worker pool started: instance {self.instance_id} with {self.min_workers} workers")
    
    async def stop(self):
        """Stop the distributed worker pool"""
        self.is_running = False
        
        # Stop all workers and deregister from cluster
        await self._scale_to_workers(0)
        await self._deregister_instance()
        
        logger.info(f"Distributed worker pool stopped: instance {self.instance_id}")
    
    async def _scaling_loop(self):
        """Continuously monitor and scale worker pool with distributed coordination"""
        while self.is_running:
            try:
                await asyncio.sleep(self.scale_check_interval)
                
                if not self.is_running:
                    break
                
                async with self.scaling_lock:
                    # Update completion rate tracking
                    self._update_completion_rate()
                    
                    # Check and scale workers with distributed coordination
                    await self._distributed_check_and_scale()
                    
            except Exception as e:
                logger.error(f"Distributed scaling loop error: {e}")
                await asyncio.sleep(5)
    
    async def _distributed_check_and_scale(self):
        """Distributed scaling with Redis-based coordination"""
        try:
            # Try to acquire distributed scaling lock
            lock_key = "cluster:scaling_lock"
            lock_acquired = await redis_client.set(lock_key, self.instance_id, nx=True, ex=30)
            
            if lock_acquired:
                # This instance leads the scaling decision
                await self._lead_scaling_decision()
            else:
                # Follow the cluster scaling decision
                await self._follow_scaling_decision()
                
        except Exception as e:
            logger.error(f"Error in distributed scaling: {e}")
    
    async def _lead_scaling_decision(self):
        """Lead scaling decision for the entire cluster"""
        try:
            # Get real-time cluster capacity
            cluster_state = await self._get_cluster_capacity()
            
            # Get queue stats
            stats = await task_manager.get_queue_stats()
            queue_length = stats["pending"]
            processing_count = stats["processing"]
            queue_pressure = queue_length + processing_count
            
            current_cluster_workers = cluster_state["active_workers"]
            max_capacity = cluster_state["max_theoretical_workers"]
            
            # Determine target cluster workers
            target_cluster_workers = await self._calculate_cluster_target(
                queue_pressure, current_cluster_workers, max_capacity
            )
            
            # Distribute workers among active instances
            active_instances = await redis_client.smembers("cluster:active_instances")
            instance_count = len(active_instances)
            
            if instance_count > 0:
                # Calculate target per instance
                base_target = target_cluster_workers // instance_count
                remainder = target_cluster_workers % instance_count
                
                # Store scaling decision in Redis for other instances
                scaling_decision = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "target_cluster_workers": target_cluster_workers,
                    "base_target_per_instance": base_target,
                    "remainder": remainder,
                    "leader_instance": self.instance_id,
                    "queue_pressure": queue_pressure
                }
                
                await redis_client.hset("cluster:scaling_decision", mapping={
                    k: str(v) for k, v in scaling_decision.items()
                })
                await redis_client.expire("cluster:scaling_decision", 60)
                
                # Apply scaling to this instance (leader gets remainder if any)
                my_target = base_target + (1 if remainder > 0 else 0)
                await self._apply_instance_scaling(my_target, "leader")
                
                logger.info(f"Led cluster scaling: {current_cluster_workers} -> {target_cluster_workers} "
                           f"across {instance_count} instances (pressure: {queue_pressure})")
            
        except Exception as e:
            logger.error(f"Error leading scaling decision: {e}")
    
    async def _follow_scaling_decision(self):
        """Follow cluster scaling decision made by leader"""
        try:
            # Get scaling decision from Redis
            decision = await redis_client.hgetall("cluster:scaling_decision")
            
            if not decision:
                # No recent scaling decision, maintain current workers
                return
            
            # Calculate this instance's target
            base_target = int(decision.get("base_target_per_instance", 0))
            remainder = int(decision.get("remainder", 0))
            
            # Get instance position to determine if it gets remainder worker
            active_instances = sorted(await redis_client.smembers("cluster:active_instances"))
            try:
                instance_index = active_instances.index(self.instance_id)
                my_target = base_target + (1 if instance_index < remainder else 0)
            except ValueError:
                # This instance not in active list, use base target
                my_target = base_target
            
            await self._apply_instance_scaling(my_target, "follower")
            
            logger.debug(f"Following cluster scaling decision: target={my_target} (base={base_target})")
            
        except Exception as e:
            logger.error(f"Error following scaling decision: {e}")
    
    async def _calculate_cluster_target(self, queue_pressure: int, current_workers: int, max_capacity: int) -> int:
        """Calculate target workers for entire cluster based on queue pressure"""
        # Get historical performance for smarter scaling
        avg_completion_rate = await self._get_cluster_completion_rate()
        
        # Gradual scaling based on queue pressure with cluster awareness
        if queue_pressure > 500:
            # Critical load - scale up aggressively but respect capacity
            target = min(current_workers + 50, max_capacity)
        elif queue_pressure > 200:
            # High load - moderate scale up
            target = min(current_workers + 25, max_capacity)
        elif queue_pressure > 100:
            # Medium load - conservative scale up
            target = min(current_workers + 15, max_capacity)
        elif queue_pressure > 50:
            # Light load - minimal scale up
            target = min(current_workers + 5, max_capacity)
        elif queue_pressure < 10:
            # Low pressure - consider scaling down with hysteresis
            consecutive_low = await self._get_cluster_consecutive_low_queue()
            if consecutive_low >= 3:
                # Scale down conservatively
                scale_down_amount = min(10, current_workers // 4)
                target = max(current_workers - scale_down_amount, self.min_workers)
                await self._reset_cluster_consecutive_low_queue()
            else:
                target = current_workers
                await self._increment_cluster_consecutive_low_queue()
        else:
            # Stable pressure
            target = current_workers
            await self._reset_cluster_consecutive_low_queue()
        
        # Ensure we don't exceed practical limits
        return max(min(target, max_capacity), self.min_workers)
    
    async def _apply_instance_scaling(self, target_workers: int, role: str):
        """Apply scaling decision to this instance"""
        current_workers = len(self.workers)
        
        if target_workers != current_workers:
            logger.info(f"Scaling instance ({role}): {current_workers} -> {target_workers}")
            await self._scale_to_workers(target_workers)
    
    async def _old_check_and_scale(self):
        """Legacy scaling method - kept for reference"""
        try:
            # Get current queue stats
            stats = await task_manager.get_queue_stats()
            queue_length = stats["pending"]
            processing_count = stats["processing"]
            current_workers = len(self.workers)
            
            # Calculate queue pressure (total workload)
            queue_pressure = queue_length + processing_count
            
            # Get available API keys count to limit max workers
            available_keys = len(api_key_manager.keys)
            if available_keys == 0:
                logger.warning("No API keys available, scaling down to minimum")
                await self._scale_to_workers(min(self.min_workers, current_workers))
                return
            
            # Enhanced API capacity calculation (assume 10-15 req/min per worker)
            total_rpm_capacity = 0
            for key_info in api_key_manager.keys:
                if not await api_key_manager.is_key_failed(key_info):
                    total_rpm_capacity += key_info.get('limits', {}).get('requests_per_minute', settings.DEFAULT_RPM)
            
            # More realistic worker capacity calculation
            optimal_workers_for_capacity = min(total_rpm_capacity // 10, self.max_workers)
            
            # Gradual scaling with improved thresholds
            target_workers = current_workers
            scale_reason = "no change"
            
            if queue_pressure > 500:
                # Critical load - scale up significantly but not to max instantly
                target_workers = min(current_workers + 25, optimal_workers_for_capacity, self.max_workers)
                scale_reason = f"critical load (pressure: {queue_pressure})"
            elif queue_pressure > 200:
                # High load - medium scale up
                target_workers = min(current_workers + 15, optimal_workers_for_capacity, self.max_workers)
                scale_reason = f"high load (pressure: {queue_pressure})"
            elif queue_pressure > 100:
                # Medium load - conservative scale up
                target_workers = min(current_workers + 10, optimal_workers_for_capacity, self.max_workers)
                scale_reason = f"medium load (pressure: {queue_pressure})"
            elif queue_pressure > 50:
                # Light load - minimal scale up
                target_workers = min(current_workers + 5, optimal_workers_for_capacity, self.max_workers)
                scale_reason = f"light load (pressure: {queue_pressure})"
            elif queue_pressure < 10:
                # Low pressure - consider scaling down with hysteresis
                self.consecutive_low_queue += 1
                if self.consecutive_low_queue >= 3:  # Require 3 consecutive low pressure readings
                    idle_workers = await self._count_idle_workers()
                    scale_down_amount = min(idle_workers // 2, 10)  # Scale down max 10 workers at a time
                    target_workers = max(current_workers - scale_down_amount, self.min_workers)
                    scale_reason = f"sustained low pressure (consecutive: {self.consecutive_low_queue}, idle: {idle_workers})"
                    # Reset counter after scaling down
                    if target_workers < current_workers:
                        self.consecutive_low_queue = 0
                else:
                    scale_reason = f"low pressure ({self.consecutive_low_queue}/3 consecutive)"
            else:
                # Reset low queue counter if pressure is not low
                self.consecutive_low_queue = 0
                scale_reason = f"stable pressure ({queue_pressure})"
            
            # Apply cooldown for major scaling events to prevent oscillation
            scaling_amount = abs(target_workers - current_workers)
            if scaling_amount > 20:
                time_since_major_scale = (datetime.now(timezone.utc) - self.last_major_scale).total_seconds()
                if time_since_major_scale < 30:  # 30 second cooldown
                    logger.debug(f"Major scaling cooldown active ({time_since_major_scale:.1f}s < 30s), skipping scale from {current_workers} to {target_workers}")
                    return
                else:
                    self.last_major_scale = datetime.now(timezone.utc)
            
            # Ensure we don't exceed capacity limits
            target_workers = min(target_workers, optimal_workers_for_capacity)
            
            # Ensure we don't go below minimum
            target_workers = max(target_workers, self.min_workers)
            
            # Log scaling decision
            if target_workers != current_workers:
                logger.info(f"Scaling workers: {current_workers} -> {target_workers} "
                           f"(queue: {queue_length}, processing: {processing_count}, pressure: {queue_pressure}) "
                           f"- Reason: {scale_reason}")
                await self._scale_to_workers(target_workers)
                
                # Track scaling history for analysis
                self.scale_history.append({
                    'timestamp': datetime.now(timezone.utc),
                    'from_workers': current_workers,
                    'to_workers': target_workers,
                    'queue_pressure': queue_pressure,
                    'reason': scale_reason
                })
                
                # Keep only last 10 scaling events
                if len(self.scale_history) > 10:
                    self.scale_history.pop(0)
            else:
                logger.debug(f"No scaling needed: {current_workers} workers, {scale_reason}")
                
        except Exception as e:
            logger.error(f"Error in scaling check: {e}")
    
    async def _get_cluster_capacity(self) -> Dict:
        """Get real-time cluster capacity from Redis state"""
        try:
            # Get available API keys from Redis (not in-memory state)
            available_keys = await self._get_available_keys_from_redis()
            
            # Calculate total RPM capacity based on Redis state
            total_capacity = 0
            for key_id in available_keys:
                # Check if key is not disabled for RPM limit
                if not await redis_client.exists(f"key_disabled_until:{key_id}:RPM"):
                    total_capacity += settings.DEFAULT_RPM
            
            # Get total active workers across all instances
            active_workers = await redis_client.scard("cluster:active_workers")
            
            # Get active instances count
            active_instances = await redis_client.scard("cluster:active_instances")
            
            return {
                "available_keys": len(available_keys),
                "total_rpm_capacity": total_capacity,
                "active_workers": active_workers,
                "active_instances": active_instances,
                "max_theoretical_workers": min(total_capacity // 10, settings.MAX_WORKERS)
            }
        except Exception as e:
            logger.error(f"Error getting cluster capacity: {e}")
            return {
                "available_keys": 0,
                "total_rpm_capacity": 0,
                "active_workers": 0,
                "active_instances": 1,
                "max_theoretical_workers": self.min_workers
            }
    
    async def _get_available_keys_from_redis(self) -> List[str]:
        """Get list of available API key IDs from Redis state"""
        try:
            available_keys = []
            
            # Get all keys from configuration
            for key_info in api_key_manager.keys:
                key_id = key_info["id"]
                
                # Skip if key is marked as failed
                if await redis_client.exists(f"key_failed:{key_id}"):
                    continue
                
                # Skip if key is disabled for any limit type
                disabled = False
                for limit_type in ["RPM", "RPD", "TPM"]:
                    if await redis_client.exists(f"key_disabled_until:{key_id}:{limit_type}"):
                        disabled = True
                        break
                
                if not disabled:
                    available_keys.append(key_id)
            
            return available_keys
            
        except Exception as e:
            logger.error(f"Error getting available keys from Redis: {e}")
            return []
    
    async def _get_cluster_completion_rate(self) -> float:
        """Get cluster-wide completion rate from Redis"""
        try:
            completion_rate = await redis_client.get("cluster:avg_completion_rate")
            return float(completion_rate) if completion_rate else 0.0
        except Exception as e:
            logger.error(f"Error getting cluster completion rate: {e}")
            return 0.0
    
    async def _get_cluster_consecutive_low_queue(self) -> int:
        """Get cluster-wide consecutive low queue count"""
        try:
            count = await redis_client.get("cluster:consecutive_low_queue")
            return int(count) if count else 0
        except Exception as e:
            logger.error(f"Error getting cluster consecutive low queue: {e}")
            return 0
    
    async def _increment_cluster_consecutive_low_queue(self):
        """Increment cluster-wide consecutive low queue count"""
        try:
            await redis_client.incr("cluster:consecutive_low_queue")
            await redis_client.expire("cluster:consecutive_low_queue", 300)  # 5 minute expiry
        except Exception as e:
            logger.error(f"Error incrementing cluster consecutive low queue: {e}")
    
    async def _reset_cluster_consecutive_low_queue(self):
        """Reset cluster-wide consecutive low queue count"""
        try:
            await redis_client.delete("cluster:consecutive_low_queue")
        except Exception as e:
            logger.error(f"Error resetting cluster consecutive low queue: {e}")

    async def _count_idle_workers(self) -> int:
        """Count workers that are currently idle"""
        idle_count = 0
        for worker in self.workers.values():
            if worker.current_task_id is None:
                idle_count += 1
        return idle_count
    
    def _get_avg_completion_rate(self) -> float:
        """Get average task completion rate (tasks per minute)"""
        if not self.completion_history:
            return 0.0
        return sum(self.completion_history) / len(self.completion_history)
    
    async def _register_instance(self):
        """Register this instance in the cluster"""
        try:
            await redis_client.sadd("cluster:active_instances", self.instance_id)
            await redis_client.expire("cluster:active_instances", 120)  # 2 minute TTL
            await self._heartbeat()
            logger.info(f"Instance {self.instance_id} registered in cluster")
        except Exception as e:
            logger.error(f"Error registering instance: {e}")
    
    async def _deregister_instance(self):
        """Deregister this instance from the cluster"""
        try:
            # Remove all workers from cluster
            worker_ids = [f"{self.instance_id}:{worker_id}" for worker_id in self.workers.keys()]
            if worker_ids:
                await redis_client.srem("cluster:active_workers", *worker_ids)
            
            # Remove instance
            await redis_client.srem("cluster:active_instances", self.instance_id)
            await redis_client.delete(f"instance:heartbeat:{self.instance_id}")
            
            logger.info(f"Instance {self.instance_id} deregistered from cluster")
        except Exception as e:
            logger.error(f"Error deregistering instance: {e}")
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeats to maintain instance registration"""
        while self.is_running:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                if self.is_running:
                    await self._heartbeat()
            except Exception as e:
                logger.error(f"Heartbeat loop error: {e}")
                await asyncio.sleep(5)
    
    async def _heartbeat(self):
        """Send heartbeat for this instance"""
        try:
            now = datetime.now(timezone.utc)
            heartbeat_data = {
                "timestamp": now.isoformat(),
                "worker_count": str(len(self.workers)),
                "active_workers": str(sum(1 for w in self.workers.values() if w.current_task_id)),
                "processed_tasks": str(sum(w.processed_tasks for w in self.workers.values()))
            }
            
            # Update heartbeat
            await redis_client.hset(f"instance:heartbeat:{self.instance_id}", mapping=heartbeat_data)
            await redis_client.expire(f"instance:heartbeat:{self.instance_id}", 120)  # 2 minute TTL
            
            # Refresh instance in active set
            await redis_client.sadd("cluster:active_instances", self.instance_id)
            await redis_client.expire("cluster:active_instances", 120)
            
            self.last_heartbeat = now
            
        except Exception as e:
            logger.error(f"Error sending heartbeat: {e}")
    
    async def _cleanup_stale_instances(self):
        """Periodically clean up stale instances and workers"""
        while self.is_running:
            try:
                await asyncio.sleep(60)  # Check every minute
                if not self.is_running:
                    break
                    
                # Get all instances
                instances = await redis_client.smembers("cluster:active_instances")
                stale_instances = []
                
                for instance_id in instances:
                    heartbeat = await redis_client.hgetall(f"instance:heartbeat:{instance_id}")
                    if not heartbeat:
                        stale_instances.append(instance_id)
                        continue
                    
                    # Check if heartbeat is too old (> 3 minutes)
                    try:
                        heartbeat_time = datetime.fromisoformat(heartbeat.get("timestamp", ""))
                        if (datetime.now(timezone.utc) - heartbeat_time).total_seconds() > 180:
                            stale_instances.append(instance_id)
                    except (ValueError, TypeError):
                        stale_instances.append(instance_id)
                
                # Clean up stale instances
                for stale_instance in stale_instances:
                    await self._cleanup_stale_instance(stale_instance)
                    
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(30)
    
    async def _cleanup_stale_instance(self, instance_id: str):
        """Clean up a stale instance and its workers"""
        try:
            # Remove instance from active set
            await redis_client.srem("cluster:active_instances", instance_id)
            
            # Remove all workers belonging to this instance
            all_workers = await redis_client.smembers("cluster:active_workers")
            stale_workers = [w for w in all_workers if w.startswith(f"{instance_id}:")]
            
            if stale_workers:
                await redis_client.srem("cluster:active_workers", *stale_workers)
                logger.info(f"Cleaned up stale instance {instance_id} and {len(stale_workers)} workers")
            
            # Clean up heartbeat
            await redis_client.delete(f"instance:heartbeat:{instance_id}")
            
        except Exception as e:
            logger.error(f"Error cleaning up stale instance {instance_id}: {e}")
    
    def _update_completion_rate(self):
        """Update completion rate history (called periodically)"""
        total_completed_now = sum(w.successful_tasks + w.failed_tasks for w in self.workers.values())
        
        # Calculate tasks completed since last update
        if hasattr(self, '_last_total_completed'):
            completed_this_period = total_completed_now - self._last_total_completed
            self.completion_history.append(completed_this_period)
            
            # Keep only last 10 periods (10 minutes of history if called every minute)
            if len(self.completion_history) > 10:
                self.completion_history.pop(0)
        
        self._last_total_completed = total_completed_now
        
        # Update cluster completion rate
        asyncio.create_task(self._update_cluster_completion_rate())
    
    async def _update_cluster_completion_rate(self):
        """Update cluster-wide completion rate in Redis"""
        try:
            # Get all instance heartbeats
            instances = await redis_client.smembers("cluster:active_instances")
            total_completion_rate = 0.0
            instance_count = 0
            
            for instance_id in instances:
                heartbeat = await redis_client.hgetall(f"instance:heartbeat:{instance_id}")
                if heartbeat:
                    # Simple approximation: processed_tasks as completion rate
                    processed = int(heartbeat.get("processed_tasks", 0))
                    total_completion_rate += processed
                    instance_count += 1
            
            if instance_count > 0:
                avg_completion_rate = total_completion_rate / instance_count
                await redis_client.set("cluster:avg_completion_rate", str(avg_completion_rate), ex=120)
            
        except Exception as e:
            logger.error(f"Error updating cluster completion rate: {e}")

    async def _calculate_scale_down_target(self, current_workers: int) -> int:
        """Calculate how many workers to scale down to based on idle time"""
        # Count idle workers (those idle for more than the configured threshold)
        idle_threshold = settings.WORKER_IDLE_THRESHOLD
        now = datetime.now(timezone.utc)
        idle_workers = 0
        
        for worker in self.workers.values():
            if worker.current_task_id is None:
                idle_time = (now - worker.last_activity).total_seconds()
                if idle_time > idle_threshold:
                    idle_workers += 1
        
        # Step-based scale down: remove workers in increments of 10-25
        if idle_workers >= 50:
            # Many idle workers - scale down by 25
            workers_to_remove = min(25, current_workers - self.min_workers)
        elif idle_workers >= 20:
            # Some idle workers - scale down by 10
            workers_to_remove = min(10, current_workers - self.min_workers)
        elif idle_workers >= 10:
            # Few idle workers - scale down by 5
            workers_to_remove = min(5, current_workers - self.min_workers)
        else:
            # Very few idle workers - minimal scaling
            workers_to_remove = min(1, current_workers - self.min_workers)
        
        target_workers = max(current_workers - workers_to_remove, self.min_workers)
        logger.debug(f"Scale down calculation: {idle_workers} idle workers, removing {workers_to_remove} ({current_workers} -> {target_workers})")
        return target_workers
    
    async def _scale_to_workers(self, target_count: int):
        """Scale worker pool to target count"""
        current_count = len(self.workers)
        
        if target_count > current_count:
            # Scale up
            workers_to_add = target_count - current_count
            for _ in range(workers_to_add):
                await self._add_worker()
                
        elif target_count < current_count:
            # Scale down
            workers_to_remove = current_count - target_count
            await self._remove_workers(workers_to_remove)
    
    async def _add_worker(self):
        """Add a new worker to the pool and register in cluster"""
        worker_id = f"worker-{uuid.uuid4().hex[:8]}"
        worker = TranslationWorker(worker_id, self)
        
        self.workers[worker_id] = worker
        
        # Register worker in cluster
        cluster_worker_id = f"{self.instance_id}:{worker_id}"
        try:
            await redis_client.sadd("cluster:active_workers", cluster_worker_id)
            await redis_client.expire("cluster:active_workers", 300)  # 5 minute TTL
        except Exception as e:
            logger.error(f"Error registering worker {worker_id} in cluster: {e}")
        
        # Start worker task
        self.worker_tasks[worker_id] = asyncio.create_task(worker.start())
        
        logger.debug(f"Added worker {worker_id} to instance {self.instance_id}")
    
    async def _remove_workers(self, count: int):
        """Remove specified number of workers from the pool"""
        # Remove idle workers first, then busy ones if needed
        workers_to_remove = []
        
        # First pass: collect idle workers
        for worker_id, worker in list(self.workers.items()):
            if len(workers_to_remove) >= count:
                break
            if worker.current_task_id is None:  # Idle worker
                workers_to_remove.append(worker_id)
        
        # Second pass: collect busy workers if we need more
        if len(workers_to_remove) < count:
            for worker_id, worker in list(self.workers.items()):
                if len(workers_to_remove) >= count:
                    break
                if worker_id not in workers_to_remove:
                    workers_to_remove.append(worker_id)
        
        # Remove selected workers
        for worker_id in workers_to_remove:
            await self._remove_worker(worker_id)
    
    async def _remove_worker(self, worker_id: str):
        """Remove a specific worker from the pool and cluster"""
        if worker_id not in self.workers:
            return
        
        worker = self.workers[worker_id]
        
        # Stop the worker
        await worker.stop()
        
        # Cancel the worker task
        if worker_id in self.worker_tasks:
            task = self.worker_tasks[worker_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self.worker_tasks[worker_id]
        
        # Remove from cluster
        cluster_worker_id = f"{self.instance_id}:{worker_id}"
        try:
            await redis_client.srem("cluster:active_workers", cluster_worker_id)
        except Exception as e:
            logger.error(f"Error deregistering worker {worker_id} from cluster: {e}")
        
        # Remove from workers dict
        del self.workers[worker_id]
        
        logger.debug(f"Removed worker {worker_id} from instance {self.instance_id}")
    
    async def get_stats(self) -> Dict[str, any]:
        """Get enhanced distributed worker pool statistics"""
        active_workers = sum(1 for w in self.workers.values() if w.current_task_id is not None)
        idle_workers = len(self.workers) - active_workers
        
        total_processed = sum(w.processed_tasks for w in self.workers.values())
        total_successful = sum(w.successful_tasks for w in self.workers.values())
        total_failed = sum(w.failed_tasks for w in self.workers.values())
        
        # Get queue stats for additional context
        queue_stats = await task_manager.get_queue_stats()
        queue_pressure = queue_stats["pending"] + queue_stats["processing"]
        
        # Get cluster-wide statistics
        cluster_state = await self._get_cluster_capacity()
        
        return {
            # Instance-specific stats
            "instance_id": self.instance_id,
            "total_workers": len(self.workers),
            "active_workers": active_workers,
            "idle_workers": idle_workers,
            "tasks_processed": total_processed,
            "tasks_successful": total_successful,
            "tasks_failed": total_failed,
            "success_rate": (total_successful / max(total_processed, 1)) * 100,
            "avg_completion_rate": self._get_avg_completion_rate(),
            "recent_scaling_events": len(self.scale_history),
            "last_scale_history": self.scale_history[-3:] if self.scale_history else [],
            
            # Cluster-wide stats
            "cluster_total_workers": cluster_state["active_workers"],
            "cluster_active_instances": cluster_state["active_instances"],
            "cluster_available_keys": cluster_state["available_keys"],
            "cluster_total_capacity": cluster_state["total_rpm_capacity"],
            "cluster_max_workers": cluster_state["max_theoretical_workers"],
            "queue_pressure": queue_pressure,
            "cluster_consecutive_low_queue": await self._get_cluster_consecutive_low_queue()
        }


# Global distributed worker pool instance
worker_pool = DistributedWorkerPool()