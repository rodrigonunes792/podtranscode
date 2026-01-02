from typing import Callable, List, Optional
import os
import re
from openai import OpenAI
from models.segment import Segment


# Words per segment for easier practice (target: 6-15 words for complete sentences)
MIN_WORDS_PER_SEGMENT = 6
MAX_WORDS_PER_SEGMENT = 15


class Transcriber:
    """Transcribes audio using OpenAI Whisper API."""

    def __init__(self, model_name: str = "whisper-1"):
        """
        Initialize the transcriber.

        Args:
            model_name: Whisper model to use (whisper-1 is the only option for API)
        """
        self.model_name = model_name
        self.client = None

    def _get_client(self):
        """Get or create OpenAI client."""
        if self.client is None:
            api_key = os.environ.get('OPENAI_API_KEY')
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            self.client = OpenAI(api_key=api_key)
        return self.client

    def transcribe(
        self,
        audio_path: str,
        language: str = "en",
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> List[Segment]:
        """
        Transcribe audio file to segments with timestamps using OpenAI API.

        Args:
            audio_path: Path to the audio file
            language: Language code (e.g., "en" for English)
            progress_callback: Optional callback(progress: 0-100, status: str)

        Returns:
            List of Segment objects with timestamps
        """
        if progress_callback:
            progress_callback(10, "Transcribing audio with OpenAI Whisper API...")

        client = self._get_client()

        # OpenAI Whisper API has a 25MB limit, so we may need to split large files
        file_size = os.path.getsize(audio_path)
        max_size = 25 * 1024 * 1024  # 25MB

        if file_size > max_size:
            if progress_callback:
                progress_callback(15, "Audio file is large, splitting into chunks...")
            result = self._transcribe_large_file(audio_path, language, progress_callback)
        else:
            with open(audio_path, "rb") as audio_file:
                response = client.audio.transcriptions.create(
                    model=self.model_name,
                    file=audio_file,
                    language=language,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"]
                )
            result = {
                'segments': [
                    {
                        'start': seg.start,
                        'end': seg.end,
                        'text': seg.text
                    }
                    for seg in response.segments
                ] if response.segments else []
            }

        segments = []
        segment_id = 0

        for i, seg in enumerate(result['segments']):
            text = seg['text'].strip()
            start = seg['start']
            end = seg['end']

            # Skip non-speech segments (music, applause, etc.)
            if self._is_non_speech(text):
                continue

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
                progress_callback(progress, f"Processing segment {i+1}/{len(result['segments'])}")

        if progress_callback:
            progress_callback(100, f"Transcription completed! {len(segments)} segments found.")

        return segments

    def _transcribe_large_file(
        self,
        audio_path: str,
        language: str,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> dict:
        """
        Transcribe a large audio file by splitting it into chunks.
        Uses pydub to split audio into ~20MB chunks.
        """
        from pydub import AudioSegment
        import tempfile

        client = self._get_client()

        # Load audio
        audio = AudioSegment.from_file(audio_path)

        # Calculate chunk duration (target ~20MB per chunk for safety margin)
        # Estimate: MP3 at 128kbps = ~1MB per minute
        # So ~20 minutes per chunk should be safe
        chunk_duration_ms = 20 * 60 * 1000  # 20 minutes in milliseconds

        chunks = []
        for i in range(0, len(audio), chunk_duration_ms):
            chunk = audio[i:i + chunk_duration_ms]
            chunks.append((i / 1000.0, chunk))  # Store start time in seconds

        all_segments = []

        for idx, (start_offset, chunk) in enumerate(chunks):
            if progress_callback:
                progress = 15 + (idx / len(chunks)) * 50
                progress_callback(progress, f"Transcribing chunk {idx + 1}/{len(chunks)}...")

            # Export chunk to temp file
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp:
                chunk.export(tmp.name, format='mp3')
                tmp_path = tmp.name

            try:
                with open(tmp_path, 'rb') as audio_file:
                    response = client.audio.transcriptions.create(
                        model=self.model_name,
                        file=audio_file,
                        language=language,
                        response_format="verbose_json",
                        timestamp_granularities=["segment"]
                    )

                # Adjust timestamps for this chunk
                if response.segments:
                    for seg in response.segments:
                        all_segments.append({
                            'start': seg.start + start_offset,
                            'end': seg.end + start_offset,
                            'text': seg.text
                        })
            finally:
                # Clean up temp file
                os.unlink(tmp_path)

        return {'segments': all_segments}

    def _split_text(self, text: str) -> List[str]:
        """
        Split text into smaller parts for easier practice.
        Keep sentences as complete as possible (target: 6-15 words).
        Only split by sentence-ending punctuation.
        """
        # Only split by sentence-ending punctuation: . ! ?
        # Keep the text more intact for better context
        parts = re.split(r'(?<=[.!?])\s+', text)
        parts = [p.strip() for p in parts if p.strip()]

        # If no splits occurred, use the original text
        if len(parts) == 0:
            parts = [text]

        # Process each part
        result = []
        for part in parts:
            words = part.split()
            word_count = len(words)

            if word_count <= MAX_WORDS_PER_SEGMENT:
                # Part is within limit, keep as is
                result.append(part)
            else:
                # Part is too long, split by commas or conjunctions
                sub_parts = self._smart_split(part)
                result.extend(sub_parts)

        # Merge small segments
        merged = []
        current = ""

        for part in result:
            part = part.strip()
            if not part:
                continue

            if not current:
                current = part
            else:
                combined = current + " " + part
                combined_words = len(combined.split())

                if combined_words <= MAX_WORDS_PER_SEGMENT:
                    current = combined
                else:
                    # Only add current if it has enough words
                    if len(current.split()) >= MIN_WORDS_PER_SEGMENT:
                        merged.append(current)
                        current = part
                    else:
                        # Force merge even if slightly over limit
                        if combined_words <= MAX_WORDS_PER_SEGMENT + 5:
                            current = combined
                        else:
                            merged.append(current)
                            current = part

        if current:
            # Handle last segment
            if len(current.split()) < MIN_WORDS_PER_SEGMENT and merged:
                last = merged.pop()
                merged.append(last + " " + current)
            else:
                merged.append(current)

        return merged if merged else [text]

    def _smart_split(self, text: str) -> List[str]:
        """Split long text intelligently by commas or natural break points."""
        words = text.split()

        # First try splitting by comma
        if ',' in text:
            parts = text.split(',')
            parts = [p.strip() for p in parts if p.strip()]

            # Merge small comma-separated parts
            result = []
            current = ""
            for part in parts:
                if not current:
                    current = part
                else:
                    combined = current + ", " + part
                    if len(combined.split()) <= MAX_WORDS_PER_SEGMENT:
                        current = combined
                    else:
                        result.append(current)
                        current = part
            if current:
                result.append(current)

            # Check if all parts are reasonable size
            if all(len(p.split()) <= MAX_WORDS_PER_SEGMENT for p in result):
                return result

        # Fall back to chunking by words if comma split didn't work
        chunks = []
        for i in range(0, len(words), MAX_WORDS_PER_SEGMENT):
            chunk = ' '.join(words[i:i + MAX_WORDS_PER_SEGMENT])
            chunks.append(chunk)
        return chunks

    def _is_non_speech(self, text: str) -> bool:
        """
        Check if text is non-speech content (music, applause, etc.).
        Whisper outputs various markers for non-speech audio.
        """
        if not text or not text.strip():
            return True

        text_lower = text.lower().strip()

        # Common non-speech markers from Whisper (with and without brackets)
        non_speech_markers = [
            # Bracketed markers
            '[music]', '[música]', '[musica]', '[music playing]',
            '[applause]', '[aplausos]', '[clapping]',
            '[laughter]', '[laughing]', '[risadas]', '[risos]',
            '[silence]', '[silêncio]', '[silencio]',
            '[inaudible]', '[inaudível]', '[inaudivel]',
            '[noise]', '[ruído]', '[ruido]', '[background noise]',
            '[crosstalk]', '[cross talk]',
            '[foreign]', '[foreign language]', '[speaking foreign language]',
            '[blank_audio]', '[blank audio]', '[no audio]',
            '[sounds]', '[sound]', '[sound effect]',
            '[breathing]', '[respiração]', '[heavy breathing]',
            '[coughing]', '[tosse]', '[cough]',
            '[sighing]', '[suspiro]', '[sigh]',
            '[singing]', '[cantando]',
            '[humming]',
            '[phone ringing]', '[bell]',
            '[door]', '[footsteps]',
            # Musical symbols
            '♪', '♫', '🎵', '🎶',
            # Common Whisper hallucinations for music
            'thank you.', 'thanks for watching',
            'please subscribe', 'like and subscribe',
            'see you next time', 'bye bye',
        ]

        # Check for markers
        for marker in non_speech_markers:
            if marker in text_lower:
                # If the text is mostly the marker, skip it
                clean_text = text_lower.replace(marker, '').strip()
                # Remove punctuation for check
                clean_text = re.sub(r'[^\w\s]', '', clean_text).strip()
                if len(clean_text) < 5:
                    return True

        # Check for bracketed content pattern [anything]
        bracketed_pattern = r'\[.*?\]'
        text_without_brackets = re.sub(bracketed_pattern, '', text).strip()
        if len(text_without_brackets) < 3:
            return True

        # Check for repeated musical notes or symbols
        if re.match(r'^[♪♫🎵🎶\s.,!?]+$', text):
            return True

        # Check for very short repeated words (common in music transcription)
        words = text_lower.split()
        if len(words) >= 3:
            unique_words = set(words)
            # If more than 70% are the same word, likely music/filler
            if len(unique_words) == 1 and len(words) >= 4:
                return True

        # Check for parentheses markers (Music), (Applause), etc.
        paren_pattern = r'\([^)]*(?:music|applause|laughter|singing|humming)[^)]*\)'
        if re.search(paren_pattern, text_lower):
            text_without_parens = re.sub(r'\([^)]*\)', '', text).strip()
            if len(text_without_parens) < 5:
                return True

        return False
