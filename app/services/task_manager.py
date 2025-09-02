import json
import base64
import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Union
from loguru import logger
from ..core.redis_client import redis_client
from ..models.schemas import TranslationTask, TaskStatus, ImageResult


class TaskManager:
    def __init__(self):
        self.task_prefix = "tasks:"
        self.queue_key = "translation_queue"
        self.processing_key = "processing_tasks"
        
    async def create_task(self, images_data: Union[bytes, List[bytes]], target_language: str) -> TranslationTask:
        """Create a new translation task and add to queue"""
        # Handle both single and multiple images
        if isinstance(images_data, bytes):
            # Single image (backward compatibility)
            images_list = [images_data]
        else:
            images_list = images_data
        
        # Encode all images to base64
        encoded_images = [base64.b64encode(img_data).decode('utf-8') for img_data in images_list]
        
        task = TranslationTask(
            target_language=target_language,
            images_data=encoded_images,
            total_images=len(encoded_images),
            partial_results=[],
            # Backward compatibility
            image_data=encoded_images[0] if encoded_images else None
        )
        
        # Initialize partial results
        task.partial_results = [
            ImageResult(index=i, status=TaskStatus.PENDING)
            for i in range(len(encoded_images))
        ]
        
        # Store task data in Redis
        task_key = f"{self.task_prefix}{task.task_id}"
        task_data = task.model_dump_json()
        
        # Set with expiration (24 hours for multiple images)
        await redis_client.set(task_key, task_data, expire=86400)
        
        # Add to queue
        await redis_client.redis.lpush(self.queue_key, task.task_id)
        
        logger.info(f"Created task {task.task_id} for language {target_language} with {len(encoded_images)} images")
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
            await redis_client.set(task_key, task_data, expire=180)
            
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
    
    async def update_partial_result(self, task_id: str, image_index: int, 
                                   result: str = None, error: str = None) -> bool:
        """Update specific image result in a multi-image task"""
        try:
            task = await self.get_task(task_id)
            if not task:
                return False
            
            # Ensure partial_results list exists and has correct size
            if not task.partial_results or len(task.partial_results) <= image_index:
                # Initialize or extend partial_results if needed
                while len(task.partial_results) <= image_index:
                    task.partial_results.append(
                        ImageResult(index=len(task.partial_results), status=TaskStatus.PENDING)
                    )
            
            # Update the specific image result
            image_result = task.partial_results[image_index]
            image_result.completed_at = datetime.now(timezone.utc)
            
            if result:
                image_result.status = TaskStatus.COMPLETED
                image_result.translated_text = result
                # Calculate processing time if task was started
                if task.started_at:
                    image_result.processing_time = (image_result.completed_at - task.started_at).total_seconds()
            else:
                image_result.status = TaskStatus.FAILED
                image_result.error = error or "Unknown error"
                # Calculate processing time if task was started
                if task.started_at:
                    image_result.processing_time = (image_result.completed_at - task.started_at).total_seconds()
            
            # Update overall task progress
            completed_count = sum(1 for r in task.partial_results if r.status in [TaskStatus.COMPLETED, TaskStatus.FAILED])
            
            # Check if all images are processed
            if completed_count >= task.total_images:
                # Check if any completed successfully
                successful_count = sum(1 for r in task.partial_results if r.status == TaskStatus.COMPLETED)
                if successful_count > 0:
                    task.status = TaskStatus.COMPLETED
                    # For backward compatibility, set translated_text to first successful result
                    for r in task.partial_results:
                        if r.status == TaskStatus.COMPLETED and r.translated_text:
                            task.translated_text = r.translated_text
                            break
                else:
                    task.status = TaskStatus.FAILED
                    # For backward compatibility, set error to first error
                    for r in task.partial_results:
                        if r.status == TaskStatus.FAILED and r.error:
                            task.error = r.error
                            break
                
                task.completed_at = datetime.now(timezone.utc)
                if task.started_at:
                    task.processing_time = (task.completed_at - task.started_at).total_seconds()
                    
                # Remove from processing set
                await redis_client.redis.srem(self.processing_key, task_id)
            
            # Save updated task
            task_key = f"{self.task_prefix}{task_id}"
            task_data = task.model_dump_json()
            await redis_client.set(task_key, task_data, expire=86400)
            
            logger.info(f"Updated task {task_id} image {image_index} status")
            return True
            
        except Exception as e:
            logger.error(f"Error updating partial result for task {task_id}: {e}")
            return False
    
    async def estimate_wait_time(self, current_queue_position: Optional[int] = None) -> int:
        """Estimate wait time based on queue length and processing capacity"""
        try:
            if current_queue_position is None:
                current_queue_position = await self.get_queue_length()
            
            if current_queue_position == 0:
                return 0
            
            # Estimate based on average processing time per image (2-3 seconds)
            avg_processing_time_per_image = 2.5  # seconds (average of 2-3 seconds)
            estimated_workers = max(1, await self.get_processing_count())
            
            # For multiple images, estimate average images per task
            avg_images_per_task = 2  # Conservative estimate
            estimated_wait = (current_queue_position * avg_processing_time_per_image * avg_images_per_task) // estimated_workers
            
            return min(max(estimated_wait, 2), 300)  # Between 2 seconds and 5 minutes
            
        except Exception as e:
            logger.error(f"Error estimating wait time: {e}")
            return 10  # Default 10 seconds
    
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