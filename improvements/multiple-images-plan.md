# MULTIPLE IMAGES TRANSLATION - IMPLEMENTATION PLAN

## Overview
Mở rộng hệ thống để hỗ trợ multiple images trong 1 request với progressive results sử dụng long polling architecture hiện tại.

## Phase 1: API Layer Changes
### File: `app/api/routes.py`
- **Modify endpoint**: `POST /translate` 
  - Thay `file: UploadFile` → `files: List[UploadFile]`
  - Add validation: max 10 images, tổng dung lượng < 50MB
  - Backward compatibility: accept both single và multiple

### New validation logic:
```python
# Validate number of files (1-10)
# Validate total file size
# Validate each file type individually
```

## Phase 2: Data Models Update
### File: `app/models/schemas.py`

#### New Models:
```python
class ImageResult(BaseModel):
    index: int = Field(description="Image index in the batch")
    status: TaskStatus = Field(description="Processing status for this image")
    translated_text: Optional[str] = Field(default=None)
    error: Optional[str] = Field(default=None) 
    completed_at: Optional[datetime] = Field(default=None)
    processing_time: Optional[float] = Field(default=None)

class TranslationTask(BaseModel):
    # Update existing fields
    images_data: List[str] = Field(description="List of base64 encoded images")
    total_images: int = Field(description="Total number of images")
    partial_results: List[ImageResult] = Field(default_factory=list)
    
    # Keep existing fields for compatibility
    image_data: Optional[str] = Field(default=None, deprecated=True)

class TaskResultResponse(BaseModel):
    # Existing fields...
    partial_results: List[ImageResult] = Field(default_factory=list)
    completed_images: int = Field(default=0)
    total_images: int = Field(default=1)
    progress_percentage: float = Field(default=0.0)
```

## Phase 3: Task Management Enhancement
### File: `app/services/task_manager.py`

#### Update `create_task()`:
```python
async def create_task(self, images_data: List[bytes], target_language: str) -> TranslationTask:
    # Encode all images to base64
    # Create task with images_data list
    # Initialize empty partial_results
    # Set total_images count
```

#### New method `update_partial_result()`:
```python
async def update_partial_result(self, task_id: str, image_index: int, 
                               result: str = None, error: str = None):
    # Update specific image result
    # Recalculate progress percentage
    # Check if all images completed
```

#### Update `estimate_wait_time()`:
```python
# Multiply by number of images
# Consider parallel processing capability
```

## Phase 4: Worker Processing Logic
### File: `app/services/worker_pool.py`

#### Update `_process_task()`:
```python
async def _process_task(self, task_id: str):
    task = await task_manager.get_task(task_id)
    
    # Process each image sequentially
    for index, image_data in enumerate(task.images_data):
        try:
            # Process single image
            success, result, error = await gemini_service.translate_image(
                base64.b64decode(image_data), task.target_language
            )
            
            # Update partial result immediately
            if success:
                await task_manager.update_partial_result(
                    task_id, index, result=result
                )
            else:
                await task_manager.update_partial_result(
                    task_id, index, error=error
                )
                
        except Exception as e:
            await task_manager.update_partial_result(
                task_id, index, error=str(e)
            )
    
    # Mark task as completed when all images processed
```

## Phase 5: Response Enhancement
### File: `app/api/routes.py`

#### Update `/result/{task_id}`:
```python
# Return immediately if any partial_results available
# Continue long polling if no results yet
# Include progress information in response

# Response format:
{
  "task_id": "...",
  "status": "processing", 
  "partial_results": [
    {"index": 0, "status": "completed", "translated_text": "...", "completed_at": "..."},
    {"index": 1, "status": "processing"},
    {"index": 2, "status": "pending"}
  ],
  "completed_images": 1,
  "total_images": 3,
  "progress_percentage": 33.33,
  "estimated_wait_time": 45
}
```

## Phase 6: Gemini Service Enhancement (Optional)
### File: `app/services/gemini_service.py`

#### Option A: Sequential Processing (Recommended)
- Keep existing `translate_image()` method
- Process images one by one for reliability
- Better error handling per image

#### Option B: Batch Processing 
- New `translate_images()` method
- Send multiple images in single API call
- Handle batch responses and errors

## Phase 7: Documentation Updates

### Update `CLAUDE.md`:
```markdown
## API Endpoints
- POST /api/v1/translate: Accept 1-10 images, return task_id
- GET /api/v1/result/{task_id}: Progressive results with partial completion

## Response Format  
- partial_results: Array of individual image results
- progress tracking: completed/total images
- backward compatible: single image still works
```

### Update `README.md`:
```markdown
### Multiple Images Translation
- Upload 1-10 images in single request
- Progressive results via long polling
- Individual image error handling

**Example:**
curl -X POST "http://localhost:8000/api/v1/translate" \
  -F "files=@image1.jpg" \
  -F "files=@image2.jpg" \
  -F "target_language=Vietnamese"
```

### Update `RUN_GUIDE.md`:
```bash
# Test multiple images
curl -X POST "http://localhost:8000/api/v1/translate" \
  -F "files=@test1.jpg" \
  -F "files=@test2.jpg" \
  -F "files=@test3.jpg" \
  -F "target_language=Vietnamese"

# Poll for progressive results  
curl "http://localhost:8000/api/v1/result/{task_id}"
# Returns partial results as they become available
```

## Phase 8: Testing Strategy

### Unit Tests:
- Multiple images validation
- Partial results storage/retrieval
- Progress calculation
- Error handling per image

### Integration Tests:
- End-to-end multiple images workflow
- Mixed success/failure scenarios
- Long polling with progressive results

### Load Tests:
- Multiple clients with multiple images
- Worker scaling under mixed load
- Memory usage with large batches

## Implementation Timeline

### Day 1: Core Changes
- [ ] Update API endpoint and validation
- [ ] Update data models and schemas
- [ ] Basic task manager modifications

### Day 2: Processing Logic
- [ ] Worker enhancement for sequential processing
- [ ] Partial results tracking
- [ ] Response format updates

### Day 3: Testing & Documentation
- [ ] Comprehensive testing
- [ ] Documentation updates
- [ ] Error handling refinement

## Backward Compatibility
- Single image requests continue to work
- Existing response fields maintained
- New fields added without breaking changes

## Performance Considerations
- Memory usage: Multiple images in Redis
- Processing time: Sequential vs parallel
- API limits: Rate limiting per batch
- Worker scaling: Adjust algorithms for longer tasks

## Error Handling Strategy
- Individual image failures don't stop batch
- Partial success scenarios well-defined
- Clear error messages per image
- Retry logic for failed images

## Key Benefits
- **Progressive Results**: Users receive results as soon as available
- **Fault Tolerance**: Individual image failures don't affect others  
- **Better UX**: No need to wait for entire batch completion
- **Backward Compatible**: Existing single image API unchanged
- **Scalable**: Leverages existing worker pool architecture

## Implementation Notes
- Maintain existing long polling mechanism
- Sequential image processing for reliability
- Redis storage for partial results
- Enhanced error handling per image
- Progress tracking and estimation