from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
import uuid
from datetime import datetime


class TranslationLanguage(str, Enum):
    VIETNAMESE = "Vietnamese"
    ENGLISH = "English"
    JAPANESE = "Japanese"
    KOREAN = "Korean"
    CHINESE_SIMPLIFIED = "Chinese (Simplified)"
    CHINESE_TRADITIONAL = "Chinese (Traditional)"
    SPANISH = "Spanish"
    FRENCH = "French"
    GERMAN = "German"
    PORTUGUESE = "Portuguese"
    RUSSIAN = "Russian"
    THAI = "Thai"
    INDONESIAN = "Indonesian"


class TranslationRequest(BaseModel):
    target_language: TranslationLanguage = Field(
        default=TranslationLanguage.VIETNAMESE,
        description="Target language for translation"
    )


class TranslationResponse(BaseModel):
    success: bool = Field(description="Whether the translation was successful")
    translated_text: Optional[str] = Field(
        default=None, 
        description="The translated text"
    )
    target_language: str = Field(description="The target language used")
    request_id: Optional[str] = Field(
        default=None,
        description="Unique request identifier for tracking"
    )
    processing_time: Optional[float] = Field(
        default=None,
        description="Processing time in seconds"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if translation failed"
    )


class ErrorResponse(BaseModel):
    detail: str = Field(description="Error description")
    request_id: Optional[str] = Field(
        default=None,
        description="Unique request identifier for tracking"
    )
    error_code: Optional[str] = Field(
        default=None,
        description="Specific error code for debugging"
    )


class HealthResponse(BaseModel):
    status: str = Field(description="Service status")
    service: str = Field(description="Service name")
    version: str = Field(description="Service version")
    redis_connected: Optional[bool] = Field(
        default=None,
        description="Redis connection status"
    )
    gemini_healthy: Optional[bool] = Field(
        default=None,
        description="Gemini API service status"
    )
    api_keys_count: Optional[int] = Field(
        default=None,
        description="Number of available API keys"
    )


class MetricsResponse(BaseModel):
    status: str = Field(description="Metrics status")
    redis_connected: bool = Field(description="Redis connection status")
    active_keys: Optional[int] = Field(
        default=None,
        description="Number of active API keys"
    )
    total_requests: Optional[int] = Field(
        default=None,
        description="Total requests processed (if available)"
    )


# Task Status Enum
class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# Task Models for Long Polling
class TranslationTask(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    target_language: str = Field(description="Target language for translation")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    image_data: Optional[str] = Field(default=None, description="Base64 encoded image data")
    translated_text: Optional[str] = Field(default=None)
    error: Optional[str] = Field(default=None)
    processing_time: Optional[float] = Field(default=None)
    worker_id: Optional[str] = Field(default=None)
    api_key_id: Optional[str] = Field(default=None)


class TaskCreationRequest(BaseModel):
    target_language: TranslationLanguage = Field(
        default=TranslationLanguage.VIETNAMESE,
        description="Target language for translation"
    )


class TaskCreationResponse(BaseModel):
    task_id: str = Field(description="Unique task identifier")
    status: TaskStatus = Field(description="Initial task status")
    estimated_processing_time: int = Field(description="Estimated processing time in seconds")


class TaskResultResponse(BaseModel):
    task_id: str = Field(description="Task identifier")
    status: TaskStatus = Field(description="Current task status")
    success: Optional[bool] = Field(default=None)
    translated_text: Optional[str] = Field(default=None)
    target_language: Optional[str] = Field(default=None)
    created_at: Optional[datetime] = Field(default=None)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    processing_time: Optional[float] = Field(default=None)
    error: Optional[str] = Field(default=None)
    estimated_wait_time: Optional[int] = Field(default=None, description="Estimated wait time for pending tasks")