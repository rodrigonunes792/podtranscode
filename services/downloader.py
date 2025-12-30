import os
import hashlib
from pathlib import Path
from typing import Callable, Optional
import yt_dlp


class PodcastDownloader:
    """Downloads podcast audio from various sources using yt-dlp."""

    def __init__(self, download_dir: str = "downloads"):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def _get_filename(self, url: str) -> str:
        """Generate a unique filename based on the URL."""
        url_hash = hashlib.md5(url.encode()).hexdigest()[:10]
        return f"podcast_{url_hash}"

    def download(
        self,
        url: str,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> str:
        """
        Download audio from the given URL.

        Args:
            url: The podcast/video URL
            progress_callback: Optional callback(progress: 0-100, status: str)

        Returns:
            Path to the downloaded audio file
        """
        filename = self._get_filename(url)
        output_path = self.download_dir / filename

        # Check if already downloaded
        mp3_path = output_path.with_suffix('.mp3')
        if mp3_path.exists():
            if progress_callback:
                progress_callback(100, "Arquivo ja existe, usando cache")
            return str(mp3_path)

        def progress_hook(d):
            if progress_callback and d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded = d.get('downloaded_bytes', 0)
                if total > 0:
                    percent = (downloaded / total) * 100
                    progress_callback(percent, f"Baixando: {percent:.1f}%")
            elif progress_callback and d['status'] == 'finished':
                progress_callback(100, "Download concluido, convertendo...")

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': str(output_path),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'progress_hooks': [progress_hook],
            'quiet': True,
            'no_warnings': True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                if progress_callback:
                    progress_callback(0, "Iniciando download...")
                ydl.download([url])

            if progress_callback:
                progress_callback(100, "Download concluido!")

            return str(mp3_path)

        except Exception as e:
            raise RuntimeError(f"Erro ao baixar podcast: {str(e)}")

    def get_info(self, url: str) -> dict:
        """Get metadata about the podcast without downloading."""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown'),
            }
