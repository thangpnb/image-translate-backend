import time
import asyncio
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request, Path
from typing import List
import magic
from loguru import logger

from ..models.schemas import (
    TranslationLanguage,
    TaskCreationResponse,
    TaskResultResponse,
    TaskStatus
)
from ..services.task_manager import task_manager
from ..core.config import settings

router = APIRouter(prefix="/translate", tags=["Translation"])

# Allowed image MIME types
ALLOWED_MIME_TYPES = {
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/webp',
    'image/bmp',
    'image/tiff'
}


@router.post("", response_model=TaskCreationResponse)
async def create_translation_task(
    request: Request,
    files: List[UploadFile] = File(None, description="Image files to translate (1-10 images)"),
    file: UploadFile = File(None, description="Single image file (backward compatibility)"),
    target_language: TranslationLanguage = Form(
        default=TranslationLanguage.VIETNAMESE,
        description="Target language for translation"
    )
):
    """
    Create a translation task and return task_id for polling
    """
    request_id = getattr(request.state, 'request_id', 'unknown')
    
    logger.info(f"Translation task creation request", extra={
        "request_id": request_id,
        "target_language": target_language.value
    })
    
    try:
        # Handle both single file (backward compatibility) and multiple files
        upload_files = []
        if files:
            upload_files = files
        elif file:
            upload_files = [file]
        else:
            raise HTTPException(status_code=400, detail="No file(s) provided")
        
        # Validate number of files
        if len(upload_files) == 0:
            raise HTTPException(status_code=400, detail="No file(s) provided")
        if len(upload_files) > 10:
            raise HTTPException(status_code=400, detail="Maximum 10 images allowed per request")
        
        # Process and validate all files
        processed_files = []
        total_size = 0
        
        for i, upload_file in enumerate(upload_files):
            if not upload_file:
                raise HTTPException(status_code=400, detail=f"File {i+1} is empty")
            
            # Read file content
            file_content = await upload_file.read()
            file_size = len(file_content)
            total_size += file_size
            
            # Check individual file size
            if file_size > settings.MAX_UPLOAD_SIZE:
                logger.warning(f"File {i+1} too large: {file_size} bytes", extra={"request_id": request_id})
                raise HTTPException(
                    status_code=413,
                    detail=f"File {i+1} too large. Maximum size: {settings.MAX_UPLOAD_SIZE} bytes"
                )
            
            processed_files.append((upload_file, file_content, file_size))
        
        # Check total size limit (50MB for multiple images)
        max_total_size = 50 * 1024 * 1024  # 50MB
        if total_size > max_total_size:
            logger.warning(f"Total files too large: {total_size} bytes", extra={"request_id": request_id})
            raise HTTPException(
                status_code=413,
                detail=f"Total files too large. Maximum total size: {max_total_size} bytes"
            )
        
        # Validate file types using python-magic
        validated_files = []
        for i, (upload_file, file_content, file_size) in enumerate(processed_files):
            try:
                mime_type = magic.from_buffer(file_content, mime=True)
            except Exception as e:
                logger.error(f"Failed to detect file type for file {i+1}: {e}", extra={"request_id": request_id})
                raise HTTPException(status_code=400, detail=f"Unable to detect file type for file {i+1}")
            
            if mime_type not in ALLOWED_MIME_TYPES:
                logger.warning(f"Invalid file type for file {i+1}: {mime_type}", extra={"request_id": request_id})
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid file type for file {i+1}: {mime_type}. Allowed types: {', '.join(ALLOWED_MIME_TYPES)}"
                )
            
            validated_files.append(file_content)
        
        logger.info(f"File validation passed for {len(validated_files)} files", extra={
            "request_id": request_id,
            "total_files": len(validated_files),
            "total_size": total_size
        })
        
        # Create translation task with multiple images
        task = await task_manager.create_task(validated_files, target_language.value)
        
        # Estimate processing time based on current queue length
        estimated_wait_time = await task_manager.estimate_wait_time()
        
        logger.info(f"Created translation task {task.task_id}", extra={
            "request_id": request_id,
            "task_id": task.task_id,
            "target_language": target_language.value,
            "total_images": len(validated_files),
            "estimated_wait_time": estimated_wait_time
        })
        
        return TaskCreationResponse(
            task_id=task.task_id,
            status=TaskStatus.PENDING,
            estimated_processing_time=estimated_wait_time
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating translation task: {e}", extra={
            "request_id": request_id
        })
        raise HTTPException(status_code=500, detail="Failed to create translation task")


@router.get("/result/{task_id}", response_model=TaskResultResponse)
async def get_translation_result(
    task_id: str = Path(..., description="Task ID to check"),
    timeout: int = 60
):
    """
    Get translation result with long polling support
    """
    if timeout > settings.POLLING_TIMEOUT:
        timeout = settings.POLLING_TIMEOUT
    
    start_time = time.time()
    
    logger.info(f"Polling request for task {task_id} with timeout {timeout}s")
    logger.error(f"DEBUG: About to call get_task for {task_id}")
    
    try:
        while time.time() - start_time < timeout:
            # Get current task status
            task = await task_manager.get_task(task_id)
            
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")
            
            # Check if any partial results are available for multi-image tasks
            if task.partial_results and len(task.partial_results) > 0:
                # Calculate progress
                completed_count = sum(1 for r in task.partial_results if r.status in [TaskStatus.COMPLETED, TaskStatus.FAILED])
                progress_percentage = (completed_count / task.total_images) * 100 if task.total_images > 0 else 0
                
                # Return immediately if any partial results are available
                if completed_count > 0 or task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                    success = task.status == TaskStatus.COMPLETED if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED] else None
                    
                    logger.info(f"Task {task_id} returning partial results: {completed_count}/{task.total_images} completed")
                    
                    return TaskResultResponse(
                        task_id=task.task_id,
                        status=task.status,
                        success=success,
                        partial_results=task.partial_results,
                        completed_images=completed_count,
                        total_images=task.total_images,
                        progress_percentage=progress_percentage,
                        # Backward compatibility
                        translated_text=task.translated_text,
                        target_language=task.target_language,
                        created_at=task.created_at,
                        started_at=task.started_at,
                        completed_at=task.completed_at,
                        processing_time=task.processing_time,
                        error=task.error
                    )
            
            # Handle single image tasks (backward compatibility)
            elif task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                success = task.status == TaskStatus.COMPLETED
                
                logger.info(f"Task {task_id} final status: {task.status.value}")
                
                return TaskResultResponse(
                    task_id=task.task_id,
                    status=task.status,
                    success=success,
                    partial_results=[],
                    completed_images=1 if success else 0,
                    total_images=1,
                    progress_percentage=100.0 if success else 0.0,
                    # Backward compatibility
                    translated_text=task.translated_text,
                    target_language=task.target_language,
                    created_at=task.created_at,
                    started_at=task.started_at,
                    completed_at=task.completed_at,
                    processing_time=task.processing_time,
                    error=task.error
                )
            
            # Task is still pending or processing, wait before checking again
            await asyncio.sleep(settings.POLLING_CHECK_INTERVAL)
        
        # Timeout reached, return current status with estimated wait time
        task = await task_manager.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        estimated_wait_time = await task_manager.estimate_wait_time()
        
        logger.info(f"Polling timeout for task {task_id}, status: {task.status.value}")
        
        # Calculate current progress for multi-image tasks
        completed_count = 0
        progress_percentage = 0.0
        if task.partial_results:
            completed_count = sum(1 for r in task.partial_results if r.status in [TaskStatus.COMPLETED, TaskStatus.FAILED])
            progress_percentage = (completed_count / task.total_images) * 100 if task.total_images > 0 else 0
        
        return TaskResultResponse(
            task_id=task.task_id,
            status=task.status,
            success=None,
            partial_results=task.partial_results or [],
            completed_images=completed_count,
            total_images=task.total_images,
            progress_percentage=progress_percentage,
            # Backward compatibility
            translated_text=None,
            target_language=task.target_language,
            created_at=task.created_at,
            started_at=task.started_at,
            completed_at=None,
            processing_time=None,
            error=None,
            estimated_wait_time=estimated_wait_time
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error polling task {task_id}: {e}")
        raise HTTPException(status_code=500, detail="Error checking task status")


@router.get("/languages")
async def get_supported_languages():
    """
    Get list of supported translation languages
    """
    languages = []
    for lang in TranslationLanguage:
        languages.append({
            "code": lang.name.lower(),
            "name": lang.value
        })
    
    return {
        "supported_languages": languages,
        "default": TranslationLanguage.VIETNAMESE.value
    }