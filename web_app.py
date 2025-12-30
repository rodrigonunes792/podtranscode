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

# Global state
processing_status = {
    'progress': 0,
    'message': 'Pronto para comecar',
    'is_processing': False,
    'segments': [],
    'audio_path': None,
    'error': None,
    'episode_id': None
}

# Services
downloader = PodcastDownloader()
transcriber = Transcriber(model_name="base")
translator = Translator(source_lang="en", target_lang="pt")


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


def process_podcast_async(url, episode_id):
    """Process podcast in background thread."""
    global processing_status

    processing_status['is_processing'] = True
    processing_status['error'] = None
    processing_status['segments'] = []
    processing_status['episode_id'] = episode_id

    try:
        # Check cache first
        cached = load_from_cache(episode_id)
        if cached:
            update_status(100, "Carregado do cache!")
            processing_status['segments'] = cached['segments']
            processing_status['audio_path'] = cached.get('audio_path')

            # Re-download audio if not exists
            if not processing_status['audio_path'] or not os.path.exists(processing_status['audio_path']):
                update_status(50, "Baixando audio novamente...")
                processing_status['audio_path'] = downloader.download(url, update_status)
                # Update cache with new audio path
                cached['audio_path'] = processing_status['audio_path']
                save_to_cache(episode_id, cached)

            update_status(100, f"Pronto! {len(cached['segments'])} frases (cache)")
            return

        # Download
        update_status(5, "Baixando podcast...")
        audio_path = downloader.download(url, update_status)
        processing_status['audio_path'] = audio_path

        # Transcribe
        update_status(20, "Transcrevendo (pode levar alguns minutos)...")
        segments = transcriber.transcribe(
            audio_path,
            language="en",
            progress_callback=update_status
        )

        # Translate
        update_status(80, "Traduzindo...")
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

        # Save to cache
        save_to_cache(episode_id, {
            'segments': segments_data,
            'audio_path': audio_path,
            'url': url
        })

        update_status(100, f"Pronto! {len(segments)} frases encontradas.")

    except Exception as e:
        processing_status['error'] = str(e)
        update_status(0, f"Erro: {str(e)}")

    finally:
        processing_status['is_processing'] = False


@app.route('/')
def index():
    """Main page."""
    return render_template('index.html')


@app.route('/api/podcast/search', methods=['POST'])
def search_podcast():
    """Search for podcast by Apple Podcasts URL or search term."""
    data = request.json
    query = data.get('query', '').strip()

    if not query:
        return jsonify({'error': 'Query nao fornecida'}), 400

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

    if not url:
        return jsonify({'error': 'URL nao fornecida'}), 400

    episode_id = get_episode_id(url)

    # Check if already cached
    cached = load_from_cache(episode_id)
    if cached:
        return jsonify({
            'status': 'cached',
            'episode_id': episode_id,
            'segment_count': len(cached['segments'])
        })

    # Start processing in background
    thread = threading.Thread(target=process_podcast_async, args=(url, episode_id), daemon=True)
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
    return jsonify({'error': 'Episodio nao encontrado no cache'}), 404


@app.route('/api/audio')
def audio():
    """Serve the audio file."""
    if processing_status['audio_path'] and os.path.exists(processing_status['audio_path']):
        return send_file(
            processing_status['audio_path'],
            mimetype='audio/mpeg'
        )
    return jsonify({'error': 'Audio nao encontrado'}), 404


if __name__ == '__main__':
    # Create folders
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    os.makedirs('cache', exist_ok=True)

    print("\n" + "="*50)
    print("PodTranscode - Pratique Ingles com Podcasts")
    print("="*50)
    print("\nAcesse no navegador: http://localhost:8080")
    print("Pressione Ctrl+C para encerrar\n")

    app.run(debug=True, port=8080, threaded=True)
