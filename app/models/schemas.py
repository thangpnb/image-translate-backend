from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


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