from pydantic_settings import BaseSettings
from typing import List, Optional
import json
import os


class Settings(BaseSettings):
    # Server Configuration
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000
    WORKERS: int = 4
    MAX_UPLOAD_SIZE: int = 10485760  # 10MB
    REQUEST_TIMEOUT: int = 300  # 5 minutes

    # CORS Configuration
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]
    CORS_ALLOW_CREDENTIALS: bool = True

    # Rate Limiting (Global)
    GLOBAL_RATE_LIMIT: int = 100  # requests per minute per IP
    BURST_RATE_LIMIT: int = 20    # burst requests

    # Redis Configuration
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None

    # Gemini Configuration
    GEMINI_MODEL: str = "gemini-2.5-flash-lite"
    API_KEYS_FILE: str = "config/api_keys.json"

    # Rate Limiting
    DEFAULT_RPM: int = 60
    DEFAULT_RPD: int = 1440
    DEFAULT_TPM: int = 32000

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_ROTATION: str = "00:00"  # Time-based rotation (daily at midnight)
    LOG_RETENTION_DAYS: int = 7

    class Config:
        env_file = ".env"
        case_sensitive = True

    def load_api_keys(self) -> dict:
        """Load API keys from JSON file"""
        try:
            if os.path.exists(self.API_KEYS_FILE):
                with open(self.API_KEYS_FILE, 'r') as f:
                    return json.load(f)
            return {"keys": []}
        except Exception as e:
            return {"keys": []}

    @property
    def redis_url(self) -> str:
        """Construct Redis URL"""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


settings = Settings()