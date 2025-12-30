import threading
import time
from typing import Callable, Optional
import pygame
from pydub import AudioSegment


class AudioPlayer:
    """Audio player with segment playback and repeat functionality."""

    def __init__(self):
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        self.audio_path: Optional[str] = None
        self.audio_data: Optional[AudioSegment] = None
        self.is_playing = False
        self.current_repeat = 0
        self.total_repeats = 1
        self._playback_thread: Optional[threading.Thread] = None
        self._stop_requested = False
        self._on_segment_complete: Optional[Callable[[], None]] = None
        self._on_repeat_change: Optional[Callable[[int, int], None]] = None

    def load(self, audio_path: str):
        """Load an audio file."""
        self.audio_path = audio_path
        self.audio_data = AudioSegment.from_file(audio_path)

    def set_callbacks(
        self,
        on_segment_complete: Optional[Callable[[], None]] = None,
        on_repeat_change: Optional[Callable[[int, int], None]] = None
    ):
        """Set callback functions."""
        self._on_segment_complete = on_segment_complete
        self._on_repeat_change = on_repeat_change

    def play_segment(
        self,
        start_ms: int,
        end_ms: int,
        repeats: int = 1
    ):
        """
        Play a specific segment of the audio.

        Args:
            start_ms: Start time in milliseconds
            end_ms: End time in milliseconds
            repeats: Number of times to repeat the segment
        """
        if self.audio_data is None:
            raise RuntimeError("No audio loaded")

        self.stop()
        self._stop_requested = False
        self.total_repeats = repeats
        self.current_repeat = 0

        def _play():
            segment = self.audio_data[start_ms:end_ms]

            # Export segment to temporary bytes
            import io
            buffer = io.BytesIO()
            segment.export(buffer, format="wav")
            buffer.seek(0)

            for repeat in range(repeats):
                if self._stop_requested:
                    break

                self.current_repeat = repeat + 1
                self.is_playing = True

                if self._on_repeat_change:
                    self._on_repeat_change(self.current_repeat, self.total_repeats)

                # Reset buffer position for each repeat
                buffer.seek(0)
                pygame.mixer.music.load(buffer)
                pygame.mixer.music.play()

                # Wait for playback to finish
                while pygame.mixer.music.get_busy() and not self._stop_requested:
                    time.sleep(0.1)

                # Small pause between repeats
                if repeat < repeats - 1 and not self._stop_requested:
                    time.sleep(0.5)

            self.is_playing = False
            if not self._stop_requested and self._on_segment_complete:
                self._on_segment_complete()

        self._playback_thread = threading.Thread(target=_play, daemon=True)
        self._playback_thread.start()

    def stop(self):
        """Stop current playback."""
        self._stop_requested = True
        pygame.mixer.music.stop()
        self.is_playing = False

        if self._playback_thread and self._playback_thread.is_alive():
            self._playback_thread.join(timeout=1.0)

    def pause(self):
        """Pause playback."""
        pygame.mixer.music.pause()
        self.is_playing = False

    def resume(self):
        """Resume playback."""
        pygame.mixer.music.unpause()
        self.is_playing = True

    def toggle_pause(self):
        """Toggle between pause and play."""
        if self.is_playing:
            self.pause()
        else:
            self.resume()

    def cleanup(self):
        """Clean up resources."""
        self.stop()
        pygame.mixer.quit()
