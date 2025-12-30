#!/usr/bin/env python3
"""
PodTranscode - Practice English with Podcasts

A desktop application that helps you learn English by listening to podcasts
with synchronized transcription and Portuguese translation.
"""

import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from ui.app import PodTranscodeApp


def main():
    """Main entry point."""
    app = PodTranscodeApp()
    app.run()


if __name__ == "__main__":
    main()
