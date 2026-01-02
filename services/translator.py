import re
from typing import Callable, List, Optional
from deep_translator import GoogleTranslator
from models.segment import Segment


class Translator:
    """Translates text using Google Translate (free)."""

    # Terms that should not be translated (technical terms, brands, etc.)
    PRESERVE_TERMS = [
        'Wi-Fi', 'WiFi', 'wi-fi', 'wifi',
        'iPhone', 'iPad', 'MacBook', 'iMac', 'iOS', 'macOS',
        'Android', 'Windows', 'Linux',
        'Bluetooth', 'USB', 'HDMI', 'GPS',
        'Google', 'Apple', 'Microsoft', 'Amazon', 'Netflix', 'Spotify',
        'Facebook', 'Instagram', 'Twitter', 'TikTok', 'YouTube', 'WhatsApp',
        'AI', 'API', 'URL', 'HTML', 'CSS', 'JavaScript', 'Python',
        'email', 'e-mail', 'online', 'offline', 'download', 'upload',
        'podcast', 'Podcast',
        'UK', 'US', 'USA', 'EU', 'UN', 'NATO', 'FBI', 'CIA', 'NASA',
        'CEO', 'CFO', 'CTO', 'PR', 'HR', 'IT', 'VIP',
        'OK', 'ok', 'DJ', 'TV', 'CD', 'DVD', 'MP3',
    ]

    def __init__(self, source_lang: str = "en", target_lang: str = "pt"):
        """
        Initialize the translator.

        Args:
            source_lang: Source language code
            target_lang: Target language code
        """
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.translator = GoogleTranslator(source=source_lang, target=target_lang)

    def _preserve_terms(self, text: str) -> tuple:
        """Replace terms to preserve with placeholders."""
        preserved = {}
        result = text
        for i, term in enumerate(self.PRESERVE_TERMS):
            placeholder = f"__PRESERVE_{i}__"
            if term in result:
                preserved[placeholder] = term
                result = result.replace(term, placeholder)
        return result, preserved

    def _restore_terms(self, text: str, preserved: dict) -> str:
        """Restore preserved terms from placeholders."""
        result = text
        for placeholder, term in preserved.items():
            result = result.replace(placeholder, term)
        return result

    def translate_text(self, text: str) -> str:
        """Translate a single text string."""
        if not text.strip():
            return ""
        try:
            # Preserve technical terms
            modified_text, preserved = self._preserve_terms(text)
            translated = self.translator.translate(modified_text)
            # Restore preserved terms
            return self._restore_terms(translated, preserved)
        except Exception as e:
            return f"[Erro na traducao: {str(e)}]"

    def translate_segments(
        self,
        segments: List[Segment],
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> List[Segment]:
        """
        Translate all segments.

        Args:
            segments: List of segments to translate
            progress_callback: Optional callback(progress: 0-100, status: str)

        Returns:
            List of segments with translations filled in
        """
        total = len(segments)

        if progress_callback:
            progress_callback(0, "Starting translation...")

        for i, segment in enumerate(segments):
            segment.translation = self.translate_text(segment.text)

            if progress_callback:
                progress = ((i + 1) / total) * 100
                progress_callback(progress, f"Translating: {i+1}/{total}")

        if progress_callback:
            progress_callback(100, "Translation completed!")

        return segments

    def translate_batch(self, texts: List[str]) -> List[str]:
        """Translate multiple texts (may be faster for many short texts)."""
        translations = []
        for text in texts:
            translations.append(self.translate_text(text))
        return translations
