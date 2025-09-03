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
            # Get the project root directory
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            prompts_file = os.path.join(project_root, "config", "prompts.yaml")
            
            if not os.path.exists(prompts_file):
                logger.warning(f"Prompts file not found at {prompts_file}, using fallback prompts")
                self._load_fallback_prompts()
                return
            
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
            self._load_fallback_prompts()
    
    def _load_fallback_prompts(self) -> None:
        """Load basic fallback prompts if configuration file is unavailable"""
        self._prompts = {
            TranslationLanguage.ENGLISH: "You are a professional game localization expert. Please extract and clean up all visible text from this image. Provide only the text content without explanations. Extract all text from the provided image:",
            TranslationLanguage.VIETNAMESE: "Bạn là chuyên gia dịch văn bản từ hình ảnh sang tiếng việt dễ hiểu cho game thủ. Hãy chỉ cung cấp bản dịch mà không giải thích gì thêm. Bây giờ hãy dịch cho tôi từ ảnh được cung cấp.",
            TranslationLanguage.JAPANESE: "あなたはプロのゲームローカライゼーションエキスパートです。この画像からすべてのテキストを抽出し、翻訳してください。説明なしに翻訳のみを提供してください。",
            TranslationLanguage.KOREAN: "당신은 전문 게임 현지화 전문가입니다. 이 이미지에서 모든 텍스트를 추출하고 번역하세요. 설명 없이 번역만 제공하세요.",
            TranslationLanguage.CHINESE_SIMPLIFIED: "您是专业的游戏本地化专家。请从此图像中提取并翻译所有文本。仅提供翻译，无需解释。",
            TranslationLanguage.CHINESE_TRADITIONAL: "您是專業的遊戲本地化專家。請從此圖像中提取並翻譯所有文本。僅提供翻譯，無需解釋。",
            TranslationLanguage.SPANISH: "Eres un experto profesional en localización de juegos. Extrae y traduce todo el texto de esta imagen. Proporciona solo la traducción sin explicaciones.",
            TranslationLanguage.FRENCH: "Vous êtes un expert professionnel en localisation de jeux. Extrayez et traduisez tout le texte de cette image. Fournissez uniquement la traduction sans explications.",
            TranslationLanguage.GERMAN: "Sie sind ein professioneller Experte für Spielelokalisierung. Extrahieren und übersetzen Sie den gesamten Text aus diesem Bild. Geben Sie nur die Übersetzung ohne Erklärungen an.",
            TranslationLanguage.PORTUGUESE: "Você é um especialista profissional em localização de jogos. Extraia e traduza todo o texto desta imagem. Forneça apenas a tradução sem explicações.",
            TranslationLanguage.RUSSIAN: "Вы профессиональный эксперт по локализации игр. Извлеките и переведите весь текст с этого изображения. Предоставьте только перевод без объяснений.",
            TranslationLanguage.THAI: "คุณเป็นผู้เชี่ยวชาญด้านการแปลเกมส์เป็นภาษาไทย กรุณาแปลข้อความทั้งหมดจากรูปภาพนี้ ให้เฉพาะการแปลเท่านั้นโดยไม่ต้องอธิบาย",
            TranslationLanguage.INDONESIAN: "Anda adalah ahli profesional lokalisasi game. Ekstrak dan terjemahkan semua teks dari gambar ini. Berikan hanya terjemahan tanpa penjelasan."
        }
        logger.warning("Using fallback prompts")
    
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