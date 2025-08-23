import sys
from loguru import logger
from .config import settings


def setup_logging():
    """Configure logging with Loguru"""
    
    # Remove default logger
    logger.remove()
    
    # Console logging with colors (always enabled)
    logger.add(
        sys.stdout,
        level=settings.LOG_LEVEL,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True
    )
    
    # Single file logging with time-based rotation (includes all levels: DEBUG, INFO, WARNING, ERROR)
    logger.add(
        "logs/app_{time:YYYY-MM-DD}.log",
        level=settings.LOG_LEVEL,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation=settings.LOG_ROTATION,  # Time-based rotation
        retention=f"{settings.LOG_RETENTION_DAYS} days",
        compression="zip",
        backtrace=True,   # Include traceback for errors
        diagnose=True,    # Include variable values in traceback
        enqueue=True      # Thread-safe logging
    )
    
    return logger