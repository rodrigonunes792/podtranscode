from dataclasses import dataclass
from typing import Optional


@dataclass
class Segment:
    """Represents a transcribed segment with timestamps and translation."""

    id: int
    start: float  # Start time in seconds
    end: float    # End time in seconds
    text: str     # Original text in English
    translation: Optional[str] = None  # Translation in Portuguese

    @property
    def duration(self) -> float:
        """Duration of the segment in seconds."""
        return self.end - self.start

    @property
    def start_ms(self) -> int:
        """Start time in milliseconds."""
        return int(self.start * 1000)

    @property
    def end_ms(self) -> int:
        """End time in milliseconds."""
        return int(self.end * 1000)

    def format_time(self, seconds: float) -> str:
        """Format seconds as MM:SS."""
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"

    @property
    def time_range(self) -> str:
        """Human-readable time range."""
        return f"{self.format_time(self.start)} - {self.format_time(self.end)}"

    def __str__(self) -> str:
        return f"[{self.time_range}] {self.text}"
