from pydantic_settings import BaseSettings
from typing import List, Optional
import yaml
import os


class Settings(BaseSettings):
    # Server Configuration
    SERVER_HOST: str
    SERVER_PORT: int
    WORKERS: int
    MAX_UPLOAD_SIZE: int
    REQUEST_TIMEOUT: int

    # CORS Configuration
    CORS_ORIGINS: List[str]
    CORS_ALLOW_CREDENTIALS: bool

    # Rate Limiting (Global)
    GLOBAL_RATE_LIMIT: int
    BURST_RATE_LIMIT: int

    # Redis Configuration
    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_DB: int
    REDIS_PASSWORD: Optional[str]

    # Gemini Configuration
    GEMINI_MODEL: str
    API_KEYS_FILE: str
    PROMPTS_FILE: str

    # Rate Limiting
    DEFAULT_RPM: int
    DEFAULT_RPD: int
    DEFAULT_TPM: int

    # Logging
    LOG_LEVEL: str
    LOG_ROTATION: str
    LOG_RETENTION_DAYS: int
    
    # Worker Pool Configuration
    MIN_WORKERS: int
    MAX_WORKERS: int
    WORKER_SCALE_CHECK_INTERVAL: int
    WORKER_IDLE_THRESHOLD: int
    
    # Long Polling Configuration
    POLLING_TIMEOUT: int
    POLLING_CHECK_INTERVAL: float
    TASK_RETENTION_TIME: int
    
    # Redis Key Expiration Settings (in seconds)
    REDIS_TASK_EXPIRE: int
    REDIS_ERROR_EXPIRE: int
    REDIS_PROCESSING_EXPIRE: int
    REDIS_RATE_LIMIT_EXPIRE: int
    REDIS_BURST_LIMIT_EXPIRE: int
    REDIS_FAILURE_COUNT_EXPIRE: int

    class Config:
        env_file = ".env"
        case_sensitive = True

    def load_api_keys(self) -> dict:
        """Load API keys from YAML file"""
        try:
            if os.path.exists(self.API_KEYS_FILE):
                with open(self.API_KEYS_FILE, 'r') as f:
                    return yaml.safe_load(f)
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