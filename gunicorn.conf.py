# Gunicorn configuration for Azure Container Apps
# Optimized for long-running tasks like Whisper transcription

import os

# Bind to port from environment variable (Azure sets PORT)
bind = f"0.0.0.0:{os.environ.get('PORT', '8080')}"

# Workers - use 1 worker to avoid memory issues with Whisper model
# Each worker loads its own Whisper model (~150MB for base)
workers = 1

# Use threads for concurrent requests within the worker
threads = 2

# Worker class - use sync for long-running CPU tasks
worker_class = "sync"

# Timeout - 10 minutes for long transcription jobs
# This is the key setting to prevent timeout errors!
timeout = 600

# Graceful timeout
graceful_timeout = 120

# Keep-alive
keepalive = 5

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Preload app to share memory between workers (if using multiple workers)
preload_app = False

# Disable max_requests to prevent worker restart during long transcriptions
# Status polling generates many requests, which would kill the worker mid-transcription
max_requests = 0
max_requests_jitter = 0
