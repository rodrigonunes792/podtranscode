from typing import Callable, List, Optional
from deep_translator import GoogleTranslator
from models.segment import Segment


class Translator:
    """Translates text using Google Translate (free)."""

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

    def translate_text(self, text: str) -> str:
        """Translate a single text string."""
        if not text.strip():
            return ""
        try:
            return self.translator.translate(text)
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
            progress_callback(0, "Iniciando traducao...")

        for i, segment in enumerate(segments):
            segment.translation = self.translate_text(segment.text)

            if progress_callback:
                progress = ((i + 1) / total) * 100
                progress_callback(progress, f"Traduzindo: {i+1}/{total}")

        if progress_callback:
            progress_callback(100, "Traducao concluida!")

        return segments

    def translate_batch(self, texts: List[str]) -> List[str]:
        """Translate multiple texts (may be faster for many short texts)."""
        translations = []
        for text in texts:
            translations.append(self.translate_text(text))
        return translations
