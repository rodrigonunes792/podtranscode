#!/usr/bin/env python3
"""
PodTranscode Web Application - Practice English with Podcasts
"""

import os
import sys
import json
import hashlib
import threading
import requests
import random
import uuid
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from services.downloader import PodcastDownloader
from services.transcriber import Transcriber
from services.translator import Translator

app = Flask(__name__, template_folder='templates', static_folder='static')

# Cache directory
CACHE_DIR = Path('cache')
CACHE_DIR.mkdir(exist_ok=True)

# Flashcards file
FLASHCARDS_FILE = CACHE_DIR / 'flashcards.json'

# Global state
processing_status = {
    'progress': 0,
    'message': 'Ready to start',
    'is_processing': False,
    'segments': [],
    'audio_path': None,
    'error': None,
    'episode_id': None
}

# Services
# browser=None means no cookies (works for public videos)
# Use browser="chrome" only for private/restricted videos
downloader = PodcastDownloader(browser=None)
transcriber = Transcriber()

# Translators for different source languages (all translate to Portuguese)
translators = {
    'en': Translator(source_lang="en", target_lang="pt"),
    'es': Translator(source_lang="es", target_lang="pt"),
}

def get_translator(source_lang):
    """Get translator for the specified source language."""
    return translators.get(source_lang, translators['en'])


def get_cache_path(episode_id):
    """Get cache file path for an episode."""
    return CACHE_DIR / f"{episode_id}.json"


def load_from_cache(episode_id):
    """Load episode data from cache if exists."""
    cache_path = get_cache_path(episode_id)
    if cache_path.exists():
        with open(cache_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def save_to_cache(episode_id, data):
    """Save episode data to cache."""
    cache_path = get_cache_path(episode_id)
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_episode_id(url):
    """Generate unique ID for an episode URL."""
    return hashlib.md5(url.encode()).hexdigest()[:16]


def update_status(progress, message):
    """Update processing status."""
    processing_status['progress'] = progress
    processing_status['message'] = message


def calculate_difficulty(segments, duration):
    """
    Calculate difficulty level based on speech characteristics.

    Criteria:
    - Words per minute (WPM): <120 Easy, 120-150 Medium, >150 Hard
    - Average words per segment
    - Presence of complex vocabulary (longer words)

    Returns: 'easy', 'medium', or 'hard'
    """
    if not segments or duration <= 0:
        return 'medium'

    # Count total words
    total_words = sum(len(seg['text'].split()) for seg in segments)

    # Words per minute
    wpm = (total_words / duration) * 60 if duration > 0 else 0

    # Average word length (complexity indicator)
    all_words = ' '.join(seg['text'] for seg in segments).split()
    avg_word_length = sum(len(w) for w in all_words) / len(all_words) if all_words else 0

    # Calculate score (higher = harder)
    score = 0

    # WPM score
    if wpm < 100:
        score += 0
    elif wpm < 130:
        score += 1
    elif wpm < 160:
        score += 2
    else:
        score += 3

    # Word length score
    if avg_word_length < 4.5:
        score += 0
    elif avg_word_length < 5.5:
        score += 1
    else:
        score += 2

    # Determine difficulty
    if score <= 1:
        return 'easy'
    elif score <= 3:
        return 'medium'
    else:
        return 'hard'


def process_podcast_async(url, episode_id, provided_title='', language='en'):
    """Process podcast in background thread."""
    global processing_status

    processing_status['is_processing'] = True
    processing_status['error'] = None
    processing_status['segments'] = []
    processing_status['episode_id'] = episode_id

    # Get appropriate translator for the source language
    translator = get_translator(language)

    try:
        # Check cache first
        cached = load_from_cache(episode_id)
        if cached:
            update_status(100, "Loaded from cache!")
            processing_status['segments'] = cached['segments']
            processing_status['audio_path'] = cached.get('audio_path')

            # Re-download audio if not exists
            if not processing_status['audio_path'] or not os.path.exists(processing_status['audio_path']):
                update_status(50, "Downloading audio again...")
                processing_status['audio_path'] = downloader.download(url, update_status)
                # Update cache with new audio path
                cached['audio_path'] = processing_status['audio_path']
                save_to_cache(episode_id, cached)

            update_status(100, f"Ready! {len(cached['segments'])} sentences (cache)")
            return

        # Get info (title, thumbnail)
        title = provided_title  # Use title from frontend if provided
        thumbnail = ""
        duration = 0
        try:
            info = downloader.get_info(url)
            if not title:  # Only use yt-dlp title if not provided from frontend
                title = info.get('title', '')
            thumbnail = info.get('thumbnail', '')
            duration = info.get('duration', 0)
        except Exception:
            pass

        # Download
        update_status(5, "Downloading podcast...")
        audio_path = downloader.download(url, update_status)
        processing_status['audio_path'] = audio_path

        # Transcribe
        update_status(20, "Transcribing (may take a few minutes)...")
        segments = transcriber.transcribe(
            audio_path,
            language=language,
            progress_callback=update_status
        )

        # Translate
        update_status(80, "Translating...")
        segments = translator.translate_segments(
            segments,
            progress_callback=update_status
        )

        # Convert to dict for JSON
        segments_data = [
            {
                'id': s.id,
                'start': s.start,
                'end': s.end,
                'start_ms': s.start_ms,
                'end_ms': s.end_ms,
                'text': s.text,
                'translation': s.translation,
                'time_range': s.time_range
            }
            for s in segments
        ]

        processing_status['segments'] = segments_data

        # Calculate difficulty based on speech characteristics
        difficulty = calculate_difficulty(segments_data, duration)

        # Save to cache
        save_to_cache(episode_id, {
            'segments': segments_data,
            'audio_path': audio_path,
            'url': url,
            'title': title,
            'thumbnail': thumbnail,
            'duration': duration,
            'difficulty': difficulty,
            'language': language
        })

        update_status(100, f"Ready! {len(segments)} sentences found.")

    except Exception as e:
        processing_status['error'] = str(e)
        update_status(0, f"Error: {str(e)}")

    finally:
        processing_status['is_processing'] = False


@app.route('/')
def index():
    """Main page."""
    return render_template('index.html')


@app.route('/api/library')
def get_library():
    """Get all cached episodes/videos."""
    library = []

    for cache_file in CACHE_DIR.glob('*.json'):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Extract first segment text as preview
            preview = ""
            if data.get('segments') and len(data['segments']) > 0:
                preview = data['segments'][0].get('text', '')[:100]

            # Get title from URL or first segment
            url = data.get('url', '')
            title = data.get('title', '')

            # Try to determine source
            source = 'Podcast'
            if 'youtube.com' in url or 'youtu.be' in url:
                source = 'YouTube'
            elif 'podcasts.apple.com' in url:
                source = 'Apple Podcasts'

            library.append({
                'id': cache_file.stem,
                'url': url,
                'title': title or preview[:50] + '...' if preview else 'Untitled',
                'preview': preview,
                'source': source,
                'segment_count': len(data.get('segments', [])),
                'thumbnail': data.get('thumbnail', ''),
                'difficulty': data.get('difficulty', 'medium'),
                'duration': data.get('duration', 0),
                'language': data.get('language', 'en'),
                'modified': cache_file.stat().st_mtime
            })
        except Exception:
            continue

    # Sort by difficulty (easy first, then medium, then hard)
    difficulty_order = {'easy': 0, 'medium': 1, 'hard': 2}
    library.sort(key=lambda x: (difficulty_order.get(x.get('difficulty', 'medium'), 1), -x['modified']))

    return jsonify({'library': library})


@app.route('/api/podcast/search', methods=['POST'])
def search_podcast():
    """Search for podcast by Apple Podcasts URL, YouTube URL, or search term."""
    data = request.json
    query = data.get('query', '').strip()

    if not query:
        return jsonify({'error': 'Query nao fornecida'}), 400

    # YouTube is not supported - redirect to Apple Podcasts
    if 'youtube.com' in query or 'youtu.be' in query:
        return jsonify({'error': 'YouTube nao e suportado. Use Apple Podcasts ou busque por nome do podcast.'}), 400

    # Check if it's an Apple Podcasts URL
    if 'podcasts.apple.com' in query:
        # Extract podcast ID from URL
        import re
        match = re.search(r'/id(\d+)', query)
        if match:
            podcast_id = match.group(1)
            # Use iTunes API to get podcast info
            response = requests.get(
                f'https://itunes.apple.com/lookup?id={podcast_id}&entity=podcastEpisode&limit=50'
            )
            if response.ok:
                data = response.json()
                results = data.get('results', [])

                if results:
                    podcast_info = results[0]
                    episodes = [
                        {
                            'id': str(ep.get('trackId', '')),
                            'title': ep.get('trackName', 'Sem titulo'),
                            'description': ep.get('description', '')[:200] + '...' if ep.get('description') else '',
                            'duration': ep.get('trackTimeMillis', 0) // 1000,
                            'date': ep.get('releaseDate', '')[:10],
                            'url': ep.get('episodeUrl', ''),
                            'cached': load_from_cache(get_episode_id(ep.get('episodeUrl', ''))) is not None
                        }
                        for ep in results[1:]  # Skip first result (podcast info)
                        if ep.get('wrapperType') == 'podcastEpisode' and ep.get('episodeUrl')
                    ]

                    return jsonify({
                        'podcast': {
                            'name': podcast_info.get('collectionName', ''),
                            'artist': podcast_info.get('artistName', ''),
                            'artwork': podcast_info.get('artworkUrl600', ''),
                        },
                        'episodes': episodes
                    })

    # Search by term
    response = requests.get(
        'https://itunes.apple.com/search',
        params={'term': query, 'entity': 'podcast', 'limit': 10}
    )

    if response.ok:
        data = response.json()
        podcasts = [
            {
                'id': str(p.get('collectionId', '')),
                'name': p.get('collectionName', ''),
                'artist': p.get('artistName', ''),
                'artwork': p.get('artworkUrl600', ''),
                'url': p.get('collectionViewUrl', '')
            }
            for p in data.get('results', [])
        ]
        return jsonify({'podcasts': podcasts})

    return jsonify({'error': 'Erro ao buscar podcasts'}), 500


@app.route('/api/process', methods=['POST'])
def process():
    """Start processing a podcast URL."""
    if processing_status['is_processing']:
        return jsonify({'error': 'Ja existe um processamento em andamento'}), 400

    data = request.json
    url = data.get('url', '').strip()
    title = data.get('title', '').strip()  # Optional title from frontend
    language = data.get('language', 'en')  # Source language (en, es, etc.)

    if not url:
        return jsonify({'error': 'URL nao fornecida'}), 400

    episode_id = get_episode_id(url)

    # Check if already cached
    cached = load_from_cache(episode_id)
    if cached:
        # Check if audio file actually exists
        audio_path = cached.get('audio_path')
        if audio_path and os.path.exists(audio_path):
            # Audio exists, use cache
            processing_status['segments'] = cached['segments']
            processing_status['audio_path'] = audio_path
            processing_status['episode_id'] = episode_id
            return jsonify({
                'status': 'cached',
                'episode_id': episode_id,
                'segment_count': len(cached['segments']),
                'language': cached.get('language', 'en')
            })
        else:
            # Audio doesn't exist, need to re-download
            # Start processing in background to re-download audio
            thread = threading.Thread(target=process_podcast_async, args=(url, episode_id, title, language), daemon=True)
            thread.start()
            return jsonify({'status': 'started', 'episode_id': episode_id, 'redownloading': True})

    # Start processing in background
    thread = threading.Thread(target=process_podcast_async, args=(url, episode_id, title, language), daemon=True)
    thread.start()

    return jsonify({'status': 'started', 'episode_id': episode_id})


@app.route('/api/status')
def status():
    """Get current processing status."""
    return jsonify({
        'progress': processing_status['progress'],
        'message': processing_status['message'],
        'is_processing': processing_status['is_processing'],
        'error': processing_status['error'],
        'segment_count': len(processing_status['segments']),
        'episode_id': processing_status['episode_id']
    })


@app.route('/api/segments')
def segments():
    """Get all processed segments."""
    return jsonify({
        'segments': processing_status['segments'],
        'audio_path': processing_status['audio_path']
    })


@app.route('/api/cache/<episode_id>')
def get_cached(episode_id):
    """Get cached episode data."""
    cached = load_from_cache(episode_id)
    if cached:
        processing_status['segments'] = cached['segments']
        processing_status['audio_path'] = cached.get('audio_path')
        return jsonify({
            'segments': cached['segments'],
            'cached': True
        })
    return jsonify({'error': 'Episode not found in cache'}), 404


@app.route('/api/cache/<episode_id>', methods=['DELETE'])
def delete_cached(episode_id):
    """Delete episode from cache."""
    cache_path = get_cache_path(episode_id)
    if cache_path.exists():
        # Also try to delete the audio file
        cached = load_from_cache(episode_id)
        if cached and cached.get('audio_path'):
            audio_path = cached.get('audio_path')
            if os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                except Exception:
                    pass
        # Delete cache file
        os.remove(cache_path)
        return jsonify({'success': True})
    return jsonify({'error': 'Episode not found in cache'}), 404


@app.route('/api/cache/<episode_id>/difficulty', methods=['PUT'])
def update_difficulty(episode_id):
    """Update episode difficulty."""
    cached = load_from_cache(episode_id)
    if not cached:
        return jsonify({'error': 'Episode not found in cache'}), 404

    data = request.json
    difficulty = data.get('difficulty', 'medium')
    if difficulty not in ['easy', 'medium', 'hard']:
        return jsonify({'error': 'Invalid difficulty'}), 400

    cached['difficulty'] = difficulty
    save_to_cache(episode_id, cached)
    return jsonify({'success': True, 'difficulty': difficulty})


@app.route('/api/audio')
def audio():
    """Serve the audio file."""
    if processing_status['audio_path'] and os.path.exists(processing_status['audio_path']):
        return send_file(
            processing_status['audio_path'],
            mimetype='audio/mpeg'
        )
    return jsonify({'error': 'Audio not found'}), 404


# ==================== FLASH CARDS API ====================

def get_user_flashcards_file(user_id: str) -> Path:
    """Get the flashcards file path for a specific user."""
    if not user_id or user_id == 'undefined':
        return FLASHCARDS_FILE
    # Sanitize user_id to prevent directory traversal
    safe_user_id = ''.join(c for c in user_id if c.isalnum() or c == '_')
    return CACHE_DIR / f'flashcards_{safe_user_id}.json'


def load_flashcards(user_id: str = None):
    """Load flashcards from file for a specific user."""
    flashcards_file = get_user_flashcards_file(user_id)
    if flashcards_file.exists():
        with open(flashcards_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def save_flashcards(flashcards, user_id: str = None):
    """Save flashcards to file for a specific user."""
    flashcards_file = get_user_flashcards_file(user_id)
    with open(flashcards_file, 'w', encoding='utf-8') as f:
        json.dump(flashcards, f, ensure_ascii=False, indent=2)


@app.route('/api/flashcards', methods=['GET'])
def get_flashcards():
    """Get all flashcards for a user."""
    user_id = request.args.get('user_id')
    flashcards = load_flashcards(user_id)
    return jsonify({'flashcards': flashcards})


@app.route('/api/flashcards', methods=['POST'])
def add_flashcard():
    """Add a new flashcard for a user."""
    user_id = request.args.get('user_id')
    data = request.json
    phrase = data.get('phrase', '').strip()
    context = data.get('context', '').strip()
    context_translation = data.get('context_translation', '').strip()

    if not phrase:
        return jsonify({'error': 'Expression not provided'}), 400

    # Translate the phrase
    try:
        translation = translator.translate_text(phrase)
    except Exception:
        translation = ''

    flashcard = {
        'id': str(uuid.uuid4())[:8],
        'phrase': phrase,
        'translation': translation,
        'context': context,
        'context_translation': context_translation,
        'created_at': import_datetime_now()
    }

    flashcards = load_flashcards(user_id)

    # Check if already exists
    if any(fc['phrase'].lower() == phrase.lower() for fc in flashcards):
        return jsonify({'error': 'This expression already exists', 'success': False}), 400

    flashcards.append(flashcard)
    save_flashcards(flashcards, user_id)

    return jsonify({'success': True, 'flashcard': flashcard})


def import_datetime_now():
    """Get current datetime as string."""
    from datetime import datetime
    return datetime.now().isoformat()


@app.route('/api/flashcards/<flashcard_id>', methods=['DELETE'])
def delete_flashcard(flashcard_id):
    """Delete a flashcard for a user."""
    user_id = request.args.get('user_id')
    flashcards = load_flashcards(user_id)
    flashcards = [fc for fc in flashcards if fc['id'] != flashcard_id]
    save_flashcards(flashcards, user_id)
    return jsonify({'success': True})


@app.route('/api/flashcards/<flashcard_id>/quiz', methods=['GET'])
def get_flashcard_quiz(flashcard_id):
    """Get quiz options for a flashcard (1 correct + 3 wrong translations)."""
    user_id = request.args.get('user_id')
    flashcards = load_flashcards(user_id)

    # Find the target flashcard
    target = None
    for fc in flashcards:
        if fc['id'] == flashcard_id:
            target = fc
            break

    if not target:
        return jsonify({'error': 'Flash card not found'}), 404

    correct_translation = target['translation']

    # Get wrong options from other flashcards or generate them
    other_translations = [
        fc['translation'] for fc in flashcards
        if fc['id'] != flashcard_id and fc['translation']
    ]

    # If we don't have enough other translations, generate some fake ones
    fake_translations = [
        "Talvez isso",
        "Outra coisa",
        "Nao sei",
        "Diferente",
        "Algo mais",
        "Nao e isso",
        "Pode ser",
        "Quem sabe"
    ]

    # Combine and pick 3 wrong options
    wrong_options = other_translations + fake_translations
    random.shuffle(wrong_options)
    wrong_options = wrong_options[:3]

    # Combine all options and shuffle
    all_options = [correct_translation] + wrong_options
    random.shuffle(all_options)

    # Find the correct index
    correct_index = all_options.index(correct_translation)

    return jsonify({
        'options': all_options,
        'correct_index': correct_index
    })


if __name__ == '__main__':
    # Create folders
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    os.makedirs('cache', exist_ok=True)

    # Get port from environment variable (for Azure) or default to 8080
    port = int(os.environ.get('PORT', 8080))

    print("\n" + "="*50)
    print("ListenUp - Practice English with Podcasts")
    print("="*50)
    print(f"\nAcesse no navegador: http://localhost:{port}")
    print("Pressione Ctrl+C para encerrar\n")

    app.run(debug=True, port=port, threaded=True)
