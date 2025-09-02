import json
import base64
import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from loguru import logger
from ..core.redis_client import redis_client
from ..models.schemas import TranslationTask, TaskStatus


class TaskManager:
    def __init__(self):
        self.task_prefix = "tasks:"
        self.queue_key = "translation_queue"
        self.processing_key = "processing_tasks"
        
    async def create_task(self, image_data: bytes, target_language: str) -> TranslationTask:
        """Create a new translation task and add to queue"""
        task = TranslationTask(
            target_language=target_language,
            image_data=base64.b64encode(image_data).decode('utf-8')
        )
        
        # Store task data in Redis
        task_key = f"{self.task_prefix}{task.task_id}"
        task_data = task.model_dump_json()
        
        # Set with expiration (24 hours)
        await redis_client.set(task_key, task_data, expire=86400)
        
        # Add to queue
        await redis_client.redis.lpush(self.queue_key, task.task_id)
        
        logger.info(f"Created task {task.task_id} for language {target_language}")
        return task
    
    async def get_task(self, task_id: str) -> Optional[TranslationTask]:
        """Get task by ID"""
        try:
            task_key = f"{self.task_prefix}{task_id}"
            task_data = await redis_client.get(task_key)
            
            if not task_data:
                return None
                
            task_dict = json.loads(task_data)
            return TranslationTask(**task_dict)
            
        except Exception as e:
            logger.error(f"Error getting task {task_id}: {e}")
            return None
    
    async def update_task_status(self, task_id: str, status: TaskStatus, **kwargs) -> bool:
        """Update task status and other fields"""
        try:
            task = await self.get_task(task_id)
            if not task:
                return False
            
            # Update task fields
            task.status = status
            
            if status == TaskStatus.PROCESSING and 'worker_id' in kwargs:
                task.started_at = datetime.now(timezone.utc)
                task.worker_id = kwargs['worker_id']
                task.api_key_id = kwargs.get('api_key_id')
                
            elif status == TaskStatus.COMPLETED:
                task.completed_at = datetime.now(timezone.utc)
                task.translated_text = kwargs.get('translated_text')
                task.processing_time = kwargs.get('processing_time')
                
                # Calculate processing time if not provided
                if not task.processing_time and task.started_at:
                    processing_time = (task.completed_at - task.started_at).total_seconds()
                    task.processing_time = processing_time
                    
            elif status == TaskStatus.FAILED:
                task.completed_at = datetime.now(timezone.utc)
                task.error = kwargs.get('error', 'Unknown error')
                task.processing_time = kwargs.get('processing_time')
                
                # Calculate processing time if not provided
                if not task.processing_time and task.started_at:
                    processing_time = (task.completed_at - task.started_at).total_seconds()
                    task.processing_time = processing_time
            
            # Update any other fields
            for key, value in kwargs.items():
                if hasattr(task, key) and key not in ['status']:
                    setattr(task, key, value)
            
            # Save updated task
            task_key = f"{self.task_prefix}{task_id}"
            task_data = task.model_dump_json()
            await redis_client.set(task_key, task_data, expire=86400)
            
            logger.info(f"Updated task {task_id} status to {status.value}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating task {task_id}: {e}")
            return False
    
    async def get_next_task(self, worker_id: str) -> Optional[str]:
        """Get next task from queue for processing"""
        try:
            # Use blocking pop with timeout to get task from queue
            result = await redis_client.redis.brpop(self.queue_key, timeout=1)
            if not result:
                return None
            
            _, task_id = result
            
            # Move task to processing set
            await redis_client.redis.sadd(self.processing_key, task_id)
            
            # Update task status to processing
            await self.update_task_status(task_id, TaskStatus.PROCESSING, worker_id=worker_id)
            
            logger.info(f"Worker {worker_id} picked up task {task_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"Error getting next task for worker {worker_id}: {e}")
            return None
    
    async def complete_task(self, task_id: str, translated_text: str, processing_time: float) -> bool:
        """Mark task as completed"""
        try:
            # Remove from processing set
            await redis_client.redis.srem(self.processing_key, task_id)
            
            # Update task status
            success = await self.update_task_status(
                task_id, 
                TaskStatus.COMPLETED,
                translated_text=translated_text,
                processing_time=processing_time
            )
            
            if success:
                logger.info(f"Task {task_id} completed successfully")
            return success
            
        except Exception as e:
            logger.error(f"Error completing task {task_id}: {e}")
            return False
    
    async def fail_task(self, task_id: str, error: str, processing_time: Optional[float] = None) -> bool:
        """Mark task as failed"""
        try:
            # Remove from processing set
            await redis_client.redis.srem(self.processing_key, task_id)
            
            # Update task status
            kwargs = {'error': error}
            if processing_time is not None:
                kwargs['processing_time'] = processing_time
                
            success = await self.update_task_status(task_id, TaskStatus.FAILED, **kwargs)
            
            if success:
                logger.info(f"Task {task_id} marked as failed: {error}")
            return success
            
        except Exception as e:
            logger.error(f"Error failing task {task_id}: {e}")
            return False
    
    async def get_queue_length(self) -> int:
        """Get current queue length"""
        try:
            return await redis_client.redis.llen(self.queue_key)
        except Exception as e:
            logger.error(f"Error getting queue length: {e}")
            return 0
    
    async def get_processing_count(self) -> int:
        """Get number of tasks currently being processed"""
        try:
            return await redis_client.redis.scard(self.processing_key)
        except Exception as e:
            logger.error(f"Error getting processing count: {e}")
            return 0
    
    async def get_queue_stats(self) -> Dict[str, int]:
        """Get comprehensive queue statistics"""
        try:
            queue_length = await self.get_queue_length()
            processing_count = await self.get_processing_count()
            
            return {
                "pending": queue_length,
                "processing": processing_count,
                "total": queue_length + processing_count
            }
        except Exception as e:
            logger.error(f"Error getting queue stats: {e}")
            return {"pending": 0, "processing": 0, "total": 0}
    
    async def estimate_wait_time(self, current_queue_position: Optional[int] = None) -> int:
        """Estimate wait time based on queue length and processing capacity"""
        try:
            if current_queue_position is None:
                current_queue_position = await self.get_queue_length()
            
            if current_queue_position == 0:
                return 0
            
            # Estimate based on average processing time and current worker capacity
            # This is a rough estimate - could be made more sophisticated
            avg_processing_time = 30  # seconds
            estimated_workers = max(1, await self.get_processing_count())
            
            # Estimate wait time based on queue position and worker capacity
            estimated_wait = (current_queue_position * avg_processing_time) // estimated_workers
            
            return min(max(estimated_wait, 5), 300)  # Between 5 seconds and 5 minutes
            
        except Exception as e:
            logger.error(f"Error estimating wait time: {e}")
            return 60  # Default 1 minute
    
    async def cleanup_stale_tasks(self, max_processing_time: int = 600) -> int:
        """Clean up stale processing tasks (older than max_processing_time seconds)"""
        try:
            cleanup_count = 0
            processing_tasks = await redis_client.redis.smembers(self.processing_key)
            
            for task_id in processing_tasks:
                task = await self.get_task(task_id)
                if not task or not task.started_at:
                    continue
                
                # Check if task has been processing for too long
                processing_duration = (datetime.now(timezone.utc) - task.started_at).total_seconds()
                
                if processing_duration > max_processing_time:
                    # Mark as failed and remove from processing
                    await self.fail_task(
                        task_id, 
                        f"Task timed out after {processing_duration:.0f} seconds",
                        processing_duration
                    )
                    cleanup_count += 1
                    logger.warning(f"Cleaned up stale task {task_id} after {processing_duration:.0f}s")
            
            return cleanup_count
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return 0


# Global task manager instance
task_manager = TaskManager()