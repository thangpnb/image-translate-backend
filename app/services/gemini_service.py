import asyncio
from typing import Optional, Tuple
from google.genai import Client
from PIL import Image
import io
from loguru import logger
from ..core.config import settings
from .key_rotation import api_key_manager


class GeminiTranslationService:
    def __init__(self):
        self.model_name = settings.GEMINI_MODEL
    
    def _get_translation_prompt(self, target_language: str) -> str:
        """Get the translation prompt optimized for specific language"""
        
        prompts = {
            "Vietnamese": """Bạn là chuyên gia dịch văn bản từ hình ảnh sang tiếng việt dễ hiểu cho game thủ.
- Hãy chỉ cung cấp bản dịch mà không giải thích gì thêm.
- Nếu bạn cảm thấy cần thiết hãy giữ nguyên tiếng anh (ví dụ tên địa danh, tên skill,...) trong bản dịch.
- Cần cẩn thận để không bỏ sót văn bản ở trong ảnh.
- Đã dịch sang tiếng việt rồi thì không cần để tiếng anh tương ứng trong bản dịch nữa.
- Cố gắng giữ nguyên layout của văn bản như trong ảnh.

Ví dụ input trong ảnh: "At Eldermar Harbor, you must attack enemies with Arcane Blink and Storm Lance to complete the mission before dawn."
Output mong muốn: "Ở Eldermar Harbor cần tấn công kẻ địch bằng Arcane Blink, Storm Lance để hoàn thành nhiệm vụ trước bình minh"

Bây giờ hãy dịch cho tôi từ ảnh được cung cấp.""",

            "Japanese": """あなたはゲーム翻訳の専門家で、画像内のテキストを日本語に翻訳します。
- 翻訳のみを提供し、説明は不要です。
- 地名やスキル名など必要に応じて英語を残してください。
- 画像内のテキストを見落とさないよう注意してください。
- レイアウトを可能な限り維持してください。
- ゲーマーにとって自然で理解しやすい日本語を使用してください。

例：「At Eldermar Harbor, you must attack enemies with Arcane Blink and Storm Lance to complete the mission before dawn.」
期待される出力：「Eldermar Harborで、Arcane BlinkとStorm Lanceで敵を攻撃し、夜明け前にミッションを完了せよ」

提供された画像を翻訳してください：""",

            "Korean": """당신은 게임 현지화 전문 번역가로, 이미지 속 텍스트를 한국어로 번역합니다.
- 번역만 제공하고 추가 설명은 하지 마세요.
- 지명이나 스킬명 등 필요시 영어를 유지하세요.
- 이미지 내 모든 텍스트를 놓치지 마세요.
- 원본 레이아웃을 최대한 유지하세요.
- 게이머들이 이해하기 쉬운 자연스러운 한국어를 사용하세요.

예시: "At Eldermar Harbor, you must attack enemies with Arcane Blink and Storm Lance to complete the mission before dawn."
기대 결과: "Eldermar Harbor에서 Arcane Blink와 Storm Lance로 적을 공격하여 새벽 전에 임무를 완료하세요"

제공된 이미지를 번역해주세요:""",

            "Chinese (Simplified)": """您是游戏本地化翻译专家，请将图像中的文本翻译成简体中文。
- 只提供翻译，无需额外解释。
- 地名、技能名等必要时保留英文。
- 仔细翻译，不要遗漏图像中的任何文本。
- 尽量保持原有排版布局。
- 使用玩家易懂的自然中文表达。

示例："At Eldermar Harbor, you must attack enemies with Arcane Blink and Storm Lance to complete the mission before dawn."
期望输出："在Eldermar Harbor，使用Arcane Blink和Storm Lance攻击敌人，在黎明前完成任务"

请翻译提供的图像：""",

            "Chinese (Traditional)": """您是遊戲本地化翻譯專家，請將圖像中的文本翻譯成繁體中文。
- 只提供翻譯，無需額外解釋。
- 地名、技能名等必要時保留英文。
- 仔細翻譯，不要遺漏圖像中的任何文本。
- 儘量保持原有排版佈局。
- 使用玩家易懂的自然中文表達。

示例："At Eldermar Harbor, you must attack enemies with Arcane Blink and Storm Lance to complete the mission before dawn."
期望輸出："在Eldermar Harbor，使用Arcane Blink和Storm Lance攻擊敵人，在黎明前完成任務"

請翻譯提供的圖像：""",

            "Thai": """คุณเป็นผู้เชี่ยวชาญในการแปลเกม กรุณาแปลข้อความในภาพเป็นภาษาไทย
- ให้เฉพาะคำแปลเท่านั้น ไม่ต้องอธิบายเพิ่มเติม
- คงชื่อสถานที่หรือสกิลเป็นภาษาอังกฤษตามความเหมาะสม
- ระวังอย่าให้ข้อความในภาพหลุดไป
- พยายามรักษารูปแบบการจัดวางข้อความ
- ใช้ภาษาไทยที่เข้าใจง่ายสำหรับเกมเมอร์

ตัวอย่าง: "At Eldermar Harbor, you must attack enemies with Arcane Blink and Storm Lance to complete the mission before dawn."
ผลลัพธ์ที่ต้องการ: "ที่ Eldermar Harbor ต้องโจมตีศัตรูด้วย Arcane Blink และ Storm Lance ให้เสร็จก่อนรุ่งสาง"

กรุณาแปลภาพที่ให้มา:""",

            "Spanish": """Eres un experto traductor especializado en localización de videojuegos.
- Proporciona solo la traducción, sin explicaciones adicionales.
- Mantén nombres de lugares y habilidades en inglés cuando sea apropiado.
- Traduce cuidadosamente todo el texto visible en la imagen.
- Mantén el diseño y formato original tanto como sea posible.
- Usa español natural y comprensible para gamers.

Ejemplo: "At Eldermar Harbor, you must attack enemies with Arcane Blink and Storm Lance to complete the mission before dawn."
Resultado esperado: "En Eldermar Harbor, debes atacar enemigos con Arcane Blink y Storm Lance para completar la misión antes del amanecer"

Traduce la imagen proporcionada:""",

            "English": """You are a professional game localization expert. Please extract and clean up all visible text from this image.
- Provide only the text content without explanations
- Maintain the original layout and formatting
- Ensure no text is missed from the image
- Present text in clear, readable format
- Keep game terminology consistent

Extract all text from the provided image:"""
        }
        
        # Default to English if language not found
        return prompts.get(target_language, prompts["English"])

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