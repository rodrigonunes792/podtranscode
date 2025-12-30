from typing import Callable, List, Optional
import re
import whisper
from models.segment import Segment


# Words per segment for easier practice (target: 5-7 words)
MIN_WORDS_PER_SEGMENT = 5
MAX_WORDS_PER_SEGMENT = 7


class Transcriber:
    """Transcribes audio using OpenAI Whisper."""

    def __init__(self, model_name: str = "base"):
        """
        Initialize the transcriber.

        Args:
            model_name: Whisper model size. Options: tiny, base, small, medium, large
                       - tiny: ~39M params, fastest, lowest quality
                       - base: ~74M params, good balance (recommended)
                       - small: ~244M params, better quality, slower
                       - medium: ~769M params, high quality, much slower
                       - large: ~1550M params, best quality, very slow
        """
        self.model_name = model_name
        self.model = None

    def load_model(self, progress_callback: Optional[Callable[[float, str], None]] = None):
        """Load the Whisper model (downloads if not cached)."""
        if self.model is not None:
            return

        if progress_callback:
            progress_callback(0, f"Carregando modelo Whisper ({self.model_name})...")

        self.model = whisper.load_model(self.model_name)

        if progress_callback:
            progress_callback(100, "Modelo carregado!")

    def transcribe(
        self,
        audio_path: str,
        language: str = "en",
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> List[Segment]:
        """
        Transcribe audio file to segments with timestamps.

        Args:
            audio_path: Path to the audio file
            language: Language code (e.g., "en" for English)
            progress_callback: Optional callback(progress: 0-100, status: str)

        Returns:
            List of Segment objects with timestamps
        """
        if self.model is None:
            self.load_model(progress_callback)

        if progress_callback:
            progress_callback(10, "Transcrevendo audio (isso pode levar alguns minutos)...")

        result = self.model.transcribe(
            audio_path,
            language=language,
            verbose=False,
            word_timestamps=False,
        )

        segments = []
        segment_id = 0

        for i, seg in enumerate(result['segments']):
            text = seg['text'].strip()
            start = seg['start']
            end = seg['end']

            # Split text into smaller parts
            parts = self._split_text(text)

            if len(parts) > 1:
                # Estimate timestamps based on character proportion
                total_chars = sum(len(p) for p in parts)
                duration = end - start
                current_time = start

                for part in parts:
                    part_duration = (len(part) / total_chars) * duration if total_chars > 0 else duration / len(parts)
                    part_end = current_time + part_duration

                    segment = Segment(
                        id=segment_id,
                        start=current_time,
                        end=part_end,
                        text=part,
                    )
                    segments.append(segment)
                    segment_id += 1
                    current_time = part_end
            else:
                segment = Segment(
                    id=segment_id,
                    start=start,
                    end=end,
                    text=text,
                )
                segments.append(segment)
                segment_id += 1

            if progress_callback:
                progress = 10 + (i / len(result['segments'])) * 90
                progress_callback(progress, f"Processando segmento {i+1}/{len(result['segments'])}")

        if progress_callback:
            progress_callback(100, f"Transcricao concluida! {len(segments)} segmentos encontrados.")

        return segments

    def _split_text(self, text: str) -> List[str]:
        """
        Split text into smaller parts for easier practice.
        Target: 5-7 words per segment.
        """
        # First split by major punctuation: . ; : ! ?
        parts = re.split(r'[.;:!?]+', text)
        parts = [p.strip() for p in parts if p.strip()]

        # Then split each part by commas
        result = []
        for part in parts:
            if ',' in part:
                sub_parts = [p.strip() for p in part.split(',') if p.strip()]
                result.extend(sub_parts)
            else:
                result.append(part)

        # Split long parts by conjunctions and enforce max words
        split_parts = []
        for part in result:
            words = part.split()
            if len(words) > MAX_WORDS_PER_SEGMENT:
                # Try to split by conjunctions
                sub_parts = self._split_by_conjunctions(part)
                for sub in sub_parts:
                    sub_words = sub.split()
                    if len(sub_words) > MAX_WORDS_PER_SEGMENT:
                        chunks = self._chunk_by_words(sub_words, MAX_WORDS_PER_SEGMENT)
                        split_parts.extend(chunks)
                    else:
                        split_parts.append(sub)
            else:
                split_parts.append(part)

        # Merge small segments to avoid isolated words (target: 5-7 words)
        final_parts = []
        current_part = ""

        for part in split_parts:
            part = part.strip()
            if not part:
                continue

            if not current_part:
                current_part = part
            else:
                combined = current_part + " " + part
                combined_words = len(combined.split())

                # If combined is within target range, merge
                if combined_words <= MAX_WORDS_PER_SEGMENT:
                    current_part = combined
                else:
                    # Current part is ready, check if it's too small
                    current_words = len(current_part.split())
                    if current_words < MIN_WORDS_PER_SEGMENT and combined_words <= MAX_WORDS_PER_SEGMENT + 2:
                        # Allow slightly longer to avoid tiny segments
                        current_part = combined
                    else:
                        final_parts.append(current_part)
                        current_part = part

        # Don't forget the last part
        if current_part:
            # If last part is too small, merge with previous if possible
            if len(current_part.split()) < MIN_WORDS_PER_SEGMENT and final_parts:
                last = final_parts.pop()
                combined = last + " " + current_part
                if len(combined.split()) <= MAX_WORDS_PER_SEGMENT + 2:
                    final_parts.append(combined)
                else:
                    final_parts.append(last)
                    final_parts.append(current_part)
            else:
                final_parts.append(current_part)

        # Clean up
        final_parts = [p.strip() for p in final_parts if p.strip()]

        return final_parts if final_parts else [text]

    def _split_by_conjunctions(self, text: str) -> List[str]:
        """Split text by common conjunctions."""
        # Pattern to split before conjunctions (keeping the conjunction with the following part)
        conjunctions = r'\b(and|but|or|so|because|when|if|that|which|where|while|although|though|since|before|after|until|unless)\b'

        # Split but keep the delimiter with the following part
        parts = re.split(f'(?={conjunctions})', text, flags=re.IGNORECASE)
        parts = [p.strip() for p in parts if p.strip()]

        return parts if len(parts) > 1 else [text]

    def _chunk_by_words(self, words: List[str], max_words: int) -> List[str]:
        """Split a list of words into chunks of max_words."""
        chunks = []
        for i in range(0, len(words), max_words):
            chunk = ' '.join(words[i:i + max_words])
            chunks.append(chunk)
        return chunks
