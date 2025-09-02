import asyncio
import uuid
import base64
from datetime import datetime, timezone
from typing import Dict, Optional, Set, List
from loguru import logger
from ..core.config import settings
from ..services.task_manager import task_manager
from ..services.gemini_service import gemini_service
from ..services.key_rotation import api_key_manager
from ..models.schemas import TaskStatus


class TranslationWorker:
    def __init__(self, worker_id: str, worker_pool: 'WorkerPool'):
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
            
            logger.info(f"Worker {self.worker_id} processing task {task_id} with {len(images_to_process)} images")
            
            # Process each image sequentially
            successful_images = 0
            failed_images = 0
            
            for index, image_data_b64 in enumerate(images_to_process):
                try:
                    # Decode image data
                    try:
                        image_data = base64.b64decode(image_data_b64)
                    except Exception as e:
                        error_msg = f"Failed to decode image {index + 1} data: {e}"
                        await task_manager.update_partial_result(task_id, index, error=error_msg)
                        failed_images += 1
                        continue
                    
                    # Perform translation for this image
                    success, result, error = await gemini_service.translate_image(
                        image_data, 
                        task.target_language
                    )
                    
                    # Update partial result immediately
                    if success:
                        await task_manager.update_partial_result(task_id, index, result=result)
                        successful_images += 1
                        logger.info(f"Worker {self.worker_id} completed image {index + 1}/{len(images_to_process)} in task {task_id}")
                    else:
                        await task_manager.update_partial_result(task_id, index, error=error or "Translation failed")
                        failed_images += 1
                        logger.warning(f"Worker {self.worker_id} failed image {index + 1} in task {task_id}: {error}")
                        
                except Exception as e:
                    error_msg = f"Exception processing image {index + 1}: {str(e)}"
                    await task_manager.update_partial_result(task_id, index, error=error_msg)
                    failed_images += 1
                    logger.error(f"Worker {self.worker_id} exception processing image {index + 1} in task {task_id}: {e}")
            
            # Update worker stats
            if successful_images > 0:
                self.successful_tasks += 1
            if failed_images == len(images_to_process):
                self.failed_tasks += 1
            
            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.info(f"Worker {self.worker_id} completed task {task_id} in {processing_time:.2f}s - {successful_images} successful, {failed_images} failed")
                
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


class WorkerPool:
    def __init__(self):
        self.min_workers = settings.MIN_WORKERS
        self.max_workers = settings.MAX_WORKERS
        self.workers: Dict[str, TranslationWorker] = {}
        self.worker_tasks: Dict[str, asyncio.Task] = {}
        self.is_running = False
        self.scaling_lock = asyncio.Lock()
        self.last_scale_check = datetime.now(timezone.utc)
        self.scale_check_interval = settings.WORKER_SCALE_CHECK_INTERVAL
        
    async def start(self):
        """Start the worker pool"""
        self.is_running = True
        
        # Start initial workers
        await self._scale_to_workers(self.min_workers)
        
        # Start scaling task
        asyncio.create_task(self._scaling_loop())
        
        logger.info(f"Worker pool started with {self.min_workers} workers")
    
    async def stop(self):
        """Stop the worker pool"""
        self.is_running = False
        
        # Stop all workers
        await self._scale_to_workers(0)
        
        logger.info("Worker pool stopped")
    
    async def _scaling_loop(self):
        """Continuously monitor and scale worker pool"""
        while self.is_running:
            try:
                await asyncio.sleep(self.scale_check_interval)
                
                if not self.is_running:
                    break
                
                async with self.scaling_lock:
                    await self._check_and_scale()
                    
            except Exception as e:
                logger.error(f"Scaling loop error: {e}")
                await asyncio.sleep(5)
    
    async def _check_and_scale(self):
        """Check queue length and scale workers accordingly"""
        try:
            # Get current queue stats
            stats = await task_manager.get_queue_stats()
            queue_length = stats["pending"]
            processing_count = stats["processing"]
            current_workers = len(self.workers)
            
            # Get available API keys count to limit max workers
            available_keys = len(api_key_manager.keys)
            if available_keys == 0:
                logger.warning("No API keys available, scaling down to minimum")
                await self._scale_to_workers(min(self.min_workers, current_workers))
                return
            
            # Calculate requests per minute capacity per key
            total_rpm_capacity = 0
            for key_info in api_key_manager.keys:
                if not await api_key_manager.is_key_failed(key_info):
                    total_rpm_capacity += key_info.get('limits', {}).get('requests_per_minute', settings.DEFAULT_RPM)
            
            # Calculate optimal worker count based on capacity and queue
            # Assume each worker can process 2 requests per minute on average
            optimal_workers_for_capacity = min(total_rpm_capacity // 2, self.max_workers)
            
            # Scale based on queue length
            if queue_length > 500:
                # Heavy load - scale to max allowed
                target_workers = min(self.max_workers, optimal_workers_for_capacity)
            elif queue_length > 100:
                # Medium load - scale up significantly
                target_workers = min(current_workers + 50, optimal_workers_for_capacity)
            elif queue_length > 20:
                # Light load - gradual scaling
                target_workers = min(current_workers + 10, optimal_workers_for_capacity)
            elif queue_length == 0 and processing_count < 10:
                # No queue and low processing - check for idle workers to scale down
                target_workers = await self._calculate_scale_down_target(current_workers)
            else:
                # Maintain current level
                target_workers = current_workers
            
            # Ensure we don't go below minimum
            target_workers = max(target_workers, self.min_workers)
            
            # Scale if needed
            if target_workers != current_workers:
                logger.info(f"Scaling workers: {current_workers} -> {target_workers} "
                           f"(queue: {queue_length}, processing: {processing_count})")
                await self._scale_to_workers(target_workers)
                
        except Exception as e:
            logger.error(f"Error in scaling check: {e}")
    
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
        
        # Scale down gradually - remove up to 25% of idle workers
        workers_to_remove = min(idle_workers // 4, current_workers - self.min_workers)
        return max(current_workers - workers_to_remove, self.min_workers)
    
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
        """Add a new worker to the pool"""
        worker_id = f"worker-{uuid.uuid4().hex[:8]}"
        worker = TranslationWorker(worker_id, self)
        
        self.workers[worker_id] = worker
        
        # Start worker task
        self.worker_tasks[worker_id] = asyncio.create_task(worker.start())
        
        logger.debug(f"Added worker {worker_id}")
    
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
        """Remove a specific worker from the pool"""
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
        
        # Remove from workers dict
        del self.workers[worker_id]
        
        logger.debug(f"Removed worker {worker_id}")
    
    async def get_stats(self) -> Dict[str, any]:
        """Get worker pool statistics"""
        active_workers = sum(1 for w in self.workers.values() if w.current_task_id is not None)
        idle_workers = len(self.workers) - active_workers
        
        total_processed = sum(w.processed_tasks for w in self.workers.values())
        total_successful = sum(w.successful_tasks for w in self.workers.values())
        total_failed = sum(w.failed_tasks for w in self.workers.values())
        
        return {
            "total_workers": len(self.workers),
            "active_workers": active_workers,
            "idle_workers": idle_workers,
            "tasks_processed": total_processed,
            "tasks_successful": total_successful,
            "tasks_failed": total_failed,
            "success_rate": (total_successful / max(total_processed, 1)) * 100
        }


# Global worker pool instance
worker_pool = WorkerPool()