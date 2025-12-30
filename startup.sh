#!/bin/bash
# Azure App Service startup script

# Install dependencies if not already installed
pip install -r requirements.txt

# Start gunicorn
gunicorn --bind=0.0.0.0:8000 --timeout 600 --workers 1 web_app:app
