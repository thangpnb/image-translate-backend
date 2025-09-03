import asyncio
from typing import Optional, Tuple
from google.genai import Client
from PIL import Image
import io
from loguru import logger
from ..core.config import settings
from .key_rotation import api_key_manager
from .prompt_manager import prompt_manager


class GeminiTranslationService:
    def __init__(self):
        self.model_name = settings.GEMINI_MODEL
    
    def _get_translation_prompt(self, target_language: str) -> str:
        """Get the translation prompt optimized for specific language"""
        return prompt_manager.get_prompt(target_language)

    async def translate_image(self, image_data: bytes, target_language: str = "Vietnamese") -> Tuple[bool, str, Optional[str]]:
        """
        Translate text in image using Gemini API
        
        Returns:
            Tuple[success: bool, result: str, error: str]
        """
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Get available API key
                key_result = await api_key_manager.get_available_key()
                if not key_result:
                    return False, "", "No API keys available"
                
                api_key, key_info = key_result
                
                # Create Gemini client
                client = Client(api_key=api_key)
                
                # Process image
                image = await self._process_image(image_data)
                if not image:
                    return False, "", "Failed to process image"
                
                # Get optimized prompt for target language
                prompt = self._get_translation_prompt(target_language)
                
                # Generate response using the correct async API
                response = await client.aio.models.generate_content(
                    model=self.model_name,
                    contents=[image, prompt],
                )
                
                # Check if response was successful
                if not response.text:
                    logger.warning("Empty response from Gemini API")
                    return False, "", "No translation generated"
                
                # Record successful usage
                estimated_tokens = len(prompt.split()) + len(response.text.split())
                await api_key_manager.record_key_usage(key_info, tokens_used=estimated_tokens)
                
                logger.info(f"Translation completed successfully using key {key_info['id']}")
                return True, response.text.strip(), None
                
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"Translation attempt {retry_count + 1} failed: {error_msg}")
                
                # Handle specific error types
                if "quota" in error_msg.lower() or "rate" in error_msg.lower():
                    # Mark key as failed due to rate limiting
                    if 'key_info' in locals():
                        await api_key_manager.mark_key_failed(key_info, failure_duration=600)  # 10 minutes
                elif "invalid" in error_msg.lower() or "unauthorized" in error_msg.lower():
                    # Mark key as failed due to authentication
                    if 'key_info' in locals():
                        await api_key_manager.mark_key_failed(key_info, failure_duration=3600)  # 1 hour
                
                retry_count += 1
                
                if retry_count < max_retries:
                    wait_time = 2 ** retry_count  # Exponential backoff
                    logger.info(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    return False, "", f"Translation failed after {max_retries} attempts: {error_msg}"
        
        return False, "", "Translation failed after maximum retries"
    
    async def _process_image(self, image_data: bytes) -> Optional[Image.Image]:
        """Process and validate image data"""
        try:
            # Open image with PIL
            image = Image.open(io.BytesIO(image_data))
            
            # Convert to RGB if necessary (for RGBA, P mode images)
            if image.mode in ('RGBA', 'P', 'LA'):
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'RGBA':
                    background.paste(image, mask=image.split()[-1])  # Use alpha channel as mask
                elif image.mode == 'P':
                    image = image.convert('RGBA')
                    background.paste(image, mask=image.split()[-1] if len(image.split()) == 4 else None)
                elif image.mode == 'LA':
                    image = image.convert('RGBA')
                    background.paste(image, mask=image.split()[-1])
                image = background
            elif image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Resize if image is too large (Gemini has size limits)
            max_size = (2048, 2048)
            if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
                image.thumbnail(max_size, Image.Resampling.LANCZOS)
                logger.info(f"Resized image to {image.size}")
            
            return image
            
        except Exception as e:
            logger.error(f"Image processing error: {e}")
            return None
    
    async def health_check(self) -> Tuple[bool, str]:
        """Check if the service is healthy"""
        try:
            key_result = await api_key_manager.get_available_key()
            if not key_result:
                return False, "No API keys available"
            
            api_key, key_info = key_result
            
            # Try to create a client instance
            client = Client(api_key=api_key)
            return True, f"Service healthy with {len(api_key_manager.keys)} API keys"
            
        except Exception as e:
            return False, f"Service unhealthy: {str(e)}"


# Global Gemini service instance
gemini_service = GeminiTranslationService()