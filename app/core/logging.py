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
    
    # File logging with rotation
    logger.add(
        "logs/app_{time:YYYY-MM-DD}.log",
        level=settings.LOG_LEVEL,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation=settings.LOG_ROTATION,
        retention=f"{settings.LOG_RETENTION_DAYS} days",
        compression="zip",
        enqueue=True  # Thread-safe logging
    )
    
    # Error file logging
    logger.add(
        "logs/errors_{time:YYYY-MM-DD}.log",
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message} | {extra}",
        rotation=settings.LOG_ROTATION,
        retention=f"{settings.LOG_RETENTION_DAYS * 2} days",  # Keep errors longer
        compression="zip",
        backtrace=True,
        diagnose=True,
        enqueue=True
    )
    
    return logger