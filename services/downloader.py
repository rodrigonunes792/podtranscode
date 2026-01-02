import os
import hashlib
from pathlib import Path
from typing import Callable, Optional
import yt_dlp


class PodcastDownloader:
    """Downloads podcast audio from various sources using yt-dlp."""

    # Supported browsers for cookie extraction
    # Chrome is recommended as Safari has macOS permission restrictions
    SUPPORTED_BROWSERS = ['chrome', 'firefox', 'edge', 'opera', 'brave', 'safari']

    def __init__(self, download_dir: str = "downloads", browser: str = None):
        """
        Initialize the downloader.

        Args:
            download_dir: Directory to save downloaded files
            browser: Browser to extract cookies from (None = no cookies).
                    Use 'chrome' for best compatibility. Safari requires
                    Full Disk Access permission on macOS.
        """
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.browser = browser.lower() if browser else None

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
                    progress_callback(percent, f"Downloading: {percent:.1f}%")
            elif progress_callback and d['status'] == 'finished':
                progress_callback(100, "Download completed, converting...")

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
            # Options to bypass YouTube bot detection
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Sec-Fetch-Mode': 'navigate',
            },
            'extractor_args': {
                'youtube': {
                    # Use multiple clients for better success rate
                    'player_client': ['ios', 'android', 'web'],
                    'player_skip': ['webpage', 'configs'],
                }
            },
            # Additional options to avoid detection
            'sleep_interval': 1,
            'max_sleep_interval': 3,
            'nocheckcertificate': True,
        }

        # Add browser cookies for authentication (private/restricted videos)
        if self.browser and self.browser in self.SUPPORTED_BROWSERS:
            ydl_opts['cookiesfrombrowser'] = (self.browser,)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                if progress_callback:
                    progress_callback(0, "Starting download...")
                ydl.download([url])

            if progress_callback:
                progress_callback(100, "Download completed!")

            return str(mp3_path)

        except Exception as e:
            raise RuntimeError(f"Error downloading podcast: {str(e)}")

    def get_info(self, url: str) -> dict:
        """Get metadata about the podcast without downloading."""
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }

        # Add browser cookies for authentication
        if self.browser and self.browser in self.SUPPORTED_BROWSERS:
            ydl_opts['cookiesfrombrowser'] = (self.browser,)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown'),
                'thumbnail': info.get('thumbnail', ''),
            }
