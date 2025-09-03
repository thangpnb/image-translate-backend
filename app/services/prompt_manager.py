import yaml
import os
from typing import Dict, Optional
from loguru import logger
from ..core.config import settings


class PromptManager:
    """Manages translation prompts loaded from configuration files"""
    
    def __init__(self):
        self._prompts: Dict[str, str] = {}
        self._load_prompts()
    
    def _load_prompts(self) -> None:
        """Load prompts from configuration file"""
        try:
            # Get the project root directory
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            prompts_file = os.path.join(project_root, "config", "prompts.yaml")
            
            if not os.path.exists(prompts_file):
                logger.warning(f"Prompts file not found at {prompts_file}, using fallback prompts")
                self._load_fallback_prompts()
                return
            
            with open(prompts_file, 'r', encoding='utf-8') as f:
                self._prompts = yaml.safe_load(f)
            
            logger.info(f"Loaded {len(self._prompts)} translation prompts from {prompts_file}")
            
        except Exception as e:
            logger.error(f"Failed to load prompts from file: {e}")
            self._load_fallback_prompts()
    
    def _load_fallback_prompts(self) -> None:
        """Load basic fallback prompts if configuration file is unavailable"""
        self._prompts = {
            "English": "You are a professional game localization expert. Please extract and clean up all visible text from this image. Provide only the text content without explanations. Extract all text from the provided image:",
            "Vietnamese": "Bạn là chuyên gia dịch văn bản từ hình ảnh sang tiếng việt dễ hiểu cho game thủ. Hãy chỉ cung cấp bản dịch mà không giải thích gì thêm. Bây giờ hãy dịch cho tôi từ ảnh được cung cấp."
        }
        logger.warning("Using fallback prompts")
    
    def get_prompt(self, target_language: str) -> str:
        """
        Get translation prompt for specific language
        
        Args:
            target_language: Target language name (e.g., "Vietnamese", "Japanese")
            
        Returns:
            Prompt string for the specified language, defaults to English if not found
        """
        prompt = self._prompts.get(target_language)
        
        if not prompt:
            logger.warning(f"Prompt not found for language '{target_language}', using English fallback")
            prompt = self._prompts.get("English", "Extract all text from the provided image:")
        
        return prompt
    
    def get_available_languages(self) -> list[str]:
        """Get list of available languages with prompts"""
        return list(self._prompts.keys())
    
    def reload_prompts(self) -> bool:
        """
        Reload prompts from configuration file
        
        Returns:
            True if reload was successful, False otherwise
        """
        try:
            old_count = len(self._prompts)
            self._load_prompts()
            new_count = len(self._prompts)
            
            logger.info(f"Prompts reloaded: {old_count} -> {new_count} languages")
            return True
            
        except Exception as e:
            logger.error(f"Failed to reload prompts: {e}")
            return False


# Global prompt manager instance
prompt_manager = PromptManager()