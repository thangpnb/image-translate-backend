import yaml
import os
from typing import Dict, Optional, Union
from loguru import logger
from ..core.config import settings
from ..models.schemas import TranslationLanguage


class PromptManager:
    """Manages translation prompts loaded from configuration files"""
    
    def __init__(self):
        self._prompts: Dict[TranslationLanguage, str] = {}
        self._load_prompts()
    
    def _load_prompts(self) -> None:
        """Load prompts from configuration file"""
        try:
            prompts_file = settings.PROMPTS_FILE
            
            if not os.path.exists(prompts_file):
                raise FileNotFoundError(f"Prompts file not found at {prompts_file}")
            
            with open(prompts_file, 'r', encoding='utf-8') as f:
                raw_prompts = yaml.safe_load(f)
                
                # Convert string keys to enum keys
                self._prompts = {}
                for lang_str, prompt in raw_prompts.items():
                    try:
                        lang_enum = TranslationLanguage(lang_str)
                        self._prompts[lang_enum] = prompt
                    except ValueError:
                        logger.warning(f"Unknown language '{lang_str}' in prompts file, skipping")
            
            logger.info(f"Loaded {len(self._prompts)} translation prompts from {prompts_file}")
            
        except Exception as e:
            logger.error(f"Failed to load prompts from file: {e}")
            raise RuntimeError(f"Could not load prompts from {settings.PROMPTS_FILE}: {e}")
    
    
    def get_prompt(self, target_language: Union[TranslationLanguage, str]) -> str:
        """
        Get translation prompt for specific language
        
        Args:
            target_language: Target language enum value or string
            
        Returns:
            Prompt string for the specified language, defaults to English if not found
        """
        # Convert string to enum if needed for backward compatibility
        if isinstance(target_language, str):
            try:
                target_language = TranslationLanguage(target_language)
            except ValueError:
                logger.warning(f"Unknown target language string '{target_language}', using English fallback")
                return self._prompts.get(TranslationLanguage.ENGLISH, "Extract all text from the provided image:")
        
        prompt = self._prompts.get(target_language)
        
        if not prompt:
            logger.warning(f"Prompt not found for language '{target_language.value}', using English fallback")
            prompt = self._prompts.get(TranslationLanguage.ENGLISH, "Extract all text from the provided image:")
        
        return prompt
    
    def get_available_languages(self) -> list[TranslationLanguage]:
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