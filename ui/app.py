import threading
import tkinter as tk
from tkinter import ttk
from typing import List, Optional
from models.segment import Segment
from services.downloader import PodcastDownloader
from services.transcriber import Transcriber
from services.translator import Translator
from services.audio_player import AudioPlayer


class PodTranscodeApp:
    """Main application window for PodTranscode."""

    def __init__(self):
        # Create main window
        self.root = tk.Tk()
        self.root.title("PodTranscode - Pratique Ingles com Podcasts")
        self.root.geometry("750x600")
        self.root.minsize(650, 500)

        # Services
        self.downloader = PodcastDownloader()
        self.transcriber = Transcriber(model_name="base")
        self.translator = Translator(source_lang="en", target_lang="pt")
        self.player = AudioPlayer()

        # State
        self.segments: List[Segment] = []
        self.current_index = 0
        self.audio_path: Optional[str] = None
        self.is_processing = False

        # Setup UI
        self._setup_ui()

        # Setup player callbacks
        self.player.set_callbacks(
            on_segment_complete=self._on_segment_complete,
            on_repeat_change=self._on_repeat_change
        )

    def _setup_ui(self):
        """Setup all UI components."""
        # Main container with padding
        main_frame = tk.Frame(self.root, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ===== URL Section =====
        url_frame = tk.Frame(main_frame)
        url_frame.pack(fill=tk.X, pady=(0, 15))

        url_label = tk.Label(url_frame, text="URL:", font=('Helvetica', 13))
        url_label.pack(side=tk.LEFT, padx=(0, 10))

        # Entry com borda visível
        entry_frame = tk.Frame(url_frame, bg='gray', bd=1, relief=tk.SOLID)
        entry_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        self.url_entry = tk.Entry(
            entry_frame,
            font=('Helvetica', 13),
            bg='white',
            fg='black',
            relief=tk.FLAT,
            highlightthickness=0
        )
        self.url_entry.pack(fill=tk.X, padx=2, pady=2)

        self.load_button = tk.Button(
            url_frame,
            text="Carregar",
            font=('Helvetica', 12),
            command=self._on_load_click
        )
        self.load_button.pack(side=tk.RIGHT)

        # ===== Progress Section =====
        progress_frame = tk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, pady=(0, 15))

        self.status_label = tk.Label(
            progress_frame,
            text="Pronto para comecar",
            font=('Helvetica', 12),
            anchor='w'
        )
        self.status_label.pack(fill=tk.X, pady=(0, 5))

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self.progress_var,
            maximum=100,
            mode='determinate'
        )
        self.progress_bar.pack(fill=tk.X)

        # ===== English Section =====
        english_frame = tk.LabelFrame(main_frame, text="English", font=('Helvetica', 12), padx=10, pady=10)
        english_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.english_header = tk.Label(
            english_frame,
            text="",
            font=('Helvetica', 10),
            fg='gray',
            anchor='w'
        )
        self.english_header.pack(fill=tk.X)

        self.english_text = tk.Text(
            english_frame,
            font=('Helvetica', 14),
            height=4,
            wrap=tk.WORD,
            relief=tk.FLAT,
            bg='#f5f5f5'
        )
        self.english_text.pack(fill=tk.BOTH, expand=True)
        self.english_text.configure(state='disabled')

        # ===== Portuguese Section =====
        portuguese_frame = tk.LabelFrame(main_frame, text="Portugues", font=('Helvetica', 12), padx=10, pady=10)
        portuguese_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        self.portuguese_text = tk.Text(
            portuguese_frame,
            font=('Helvetica', 14),
            height=4,
            wrap=tk.WORD,
            relief=tk.FLAT,
            bg='#f0fff0',
            fg='#006400'
        )
        self.portuguese_text.pack(fill=tk.BOTH, expand=True)
        self.portuguese_text.configure(state='disabled')

        # ===== Controls Section =====
        controls_frame = tk.Frame(main_frame)
        controls_frame.pack(fill=tk.X)

        # Left: Repeats
        left_frame = tk.Frame(controls_frame)
        left_frame.pack(side=tk.LEFT)

        repeat_label = tk.Label(left_frame, text="Repeticoes:", font=('Helvetica', 12))
        repeat_label.pack(side=tk.LEFT, padx=(0, 5))

        self.repeat_var = tk.StringVar(value="3")
        self.repeat_menu = ttk.Combobox(
            left_frame,
            textvariable=self.repeat_var,
            values=["1", "2", "3", "4", "5"],
            width=5,
            state="readonly",
            font=('Helvetica', 12)
        )
        self.repeat_menu.pack(side=tk.LEFT)

        # Center: Navigation buttons
        center_frame = tk.Frame(controls_frame)
        center_frame.pack(side=tk.LEFT, expand=True)

        self.prev_button = tk.Button(
            center_frame,
            text="< Anterior",
            font=('Helvetica', 12),
            width=10,
            command=self._on_prev_click
        )
        self.prev_button.pack(side=tk.LEFT, padx=5)

        self.play_button = tk.Button(
            center_frame,
            text="Play",
            font=('Helvetica', 12, 'bold'),
            width=10,
            bg='#4CAF50',
            fg='white',
            activebackground='#45a049',
            command=self._on_play_click
        )
        self.play_button.pack(side=tk.LEFT, padx=5)

        self.next_button = tk.Button(
            center_frame,
            text="Proxima >",
            font=('Helvetica', 12),
            width=10,
            command=self._on_next_click
        )
        self.next_button.pack(side=tk.LEFT, padx=5)

        # Right: Info
        right_frame = tk.Frame(controls_frame)
        right_frame.pack(side=tk.RIGHT)

        self.segment_label = tk.Label(right_frame, text="Frase 0 de 0", font=('Helvetica', 12))
        self.segment_label.pack()

        self.repeat_status_label = tk.Label(right_frame, text="", font=('Helvetica', 10), fg='gray')
        self.repeat_status_label.pack()

        # Disable controls initially
        self._set_controls_enabled(False)

    def _set_controls_enabled(self, enabled: bool):
        """Enable or disable playback controls."""
        state = tk.NORMAL if enabled else tk.DISABLED
        self.prev_button.configure(state=state)
        self.play_button.configure(state=state)
        self.next_button.configure(state=state)
        self.repeat_menu.configure(state="readonly" if enabled else "disabled")

    def _update_status(self, progress: float, message: str):
        """Update progress bar and status message (thread-safe)."""
        self.root.after(0, lambda: self._do_update_status(progress, message))

    def _do_update_status(self, progress: float, message: str):
        """Actually update the UI."""
        self.progress_var.set(progress)
        self.status_label.configure(text=message)

    def _update_text_display(self):
        """Update the text display with current segment."""
        if not self.segments or self.current_index >= len(self.segments):
            return

        segment = self.segments[self.current_index]

        # Update English text
        self.english_text.configure(state='normal')
        self.english_text.delete("1.0", tk.END)
        self.english_text.insert("1.0", segment.text)
        self.english_text.configure(state='disabled')

        # Update Portuguese text
        self.portuguese_text.configure(state='normal')
        self.portuguese_text.delete("1.0", tk.END)
        self.portuguese_text.insert("1.0", segment.translation or "")
        self.portuguese_text.configure(state='disabled')

        # Update labels
        self.segment_label.configure(text=f"Frase {self.current_index + 1} de {len(self.segments)}")
        self.english_header.configure(text=f"[{segment.time_range}]")

    def _on_load_click(self):
        """Handle load button click."""
        url = self.url_entry.get().strip()
        if not url:
            self.status_label.configure(text="Por favor, insira uma URL")
            return

        if self.is_processing:
            return

        self.is_processing = True
        self.load_button.configure(state=tk.DISABLED)
        self._set_controls_enabled(False)

        thread = threading.Thread(target=self._process_podcast, args=(url,), daemon=True)
        thread.start()

    def _process_podcast(self, url: str):
        """Process podcast: download, transcribe, translate."""
        try:
            self._update_status(0, "Baixando podcast...")
            self.audio_path = self.downloader.download(url, self._update_status)

            self._update_status(0, "Carregando audio...")
            self.player.load(self.audio_path)

            self._update_status(0, "Transcrevendo (pode levar alguns minutos)...")
            self.segments = self.transcriber.transcribe(
                self.audio_path,
                language="en",
                progress_callback=self._update_status
            )

            self._update_status(0, "Traduzindo...")
            self.segments = self.translator.translate_segments(
                self.segments,
                progress_callback=self._update_status
            )

            self.current_index = 0
            self._update_status(100, f"Pronto! {len(self.segments)} frases encontradas.")
            self.root.after(0, self._on_processing_complete)

        except Exception as e:
            self._update_status(0, f"Erro: {str(e)}")
            self.root.after(0, self._on_processing_error)

    def _on_processing_complete(self):
        """Called when processing is complete."""
        self.is_processing = False
        self.load_button.configure(state=tk.NORMAL)
        self._set_controls_enabled(True)
        self._update_text_display()

    def _on_processing_error(self):
        """Called when processing encounters an error."""
        self.is_processing = False
        self.load_button.configure(state=tk.NORMAL)

    def _on_play_click(self):
        """Handle play button click."""
        if not self.segments:
            return

        if self.player.is_playing:
            self.player.stop()
            self.play_button.configure(text="Play", bg='#4CAF50')
            return

        segment = self.segments[self.current_index]
        repeats = int(self.repeat_var.get())

        self.player.play_segment(segment.start_ms, segment.end_ms, repeats=repeats)
        self.play_button.configure(text="Stop", bg='#f44336')

    def _on_prev_click(self):
        """Handle previous button click."""
        if self.current_index > 0:
            self.player.stop()
            self.current_index -= 1
            self._update_text_display()
            self.repeat_status_label.configure(text="")
            self.play_button.configure(text="Play", bg='#4CAF50')

    def _on_next_click(self):
        """Handle next button click."""
        if self.current_index < len(self.segments) - 1:
            self.player.stop()
            self.current_index += 1
            self._update_text_display()
            self.repeat_status_label.configure(text="")
            self.play_button.configure(text="Play", bg='#4CAF50')

    def _on_segment_complete(self):
        """Called when segment playback completes."""
        self.root.after(0, lambda: self.play_button.configure(text="Play", bg='#4CAF50'))
        self.root.after(0, lambda: self.repeat_status_label.configure(text=""))

    def _on_repeat_change(self, current: int, total: int):
        """Called when repeat count changes."""
        self.root.after(0, lambda: self.repeat_status_label.configure(
            text=f"Repeticao {current} de {total}"
        ))

    def on_closing(self):
        """Handle window close."""
        self.player.cleanup()
        self.root.destroy()

    def run(self):
        """Run the application."""
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.mainloop()
