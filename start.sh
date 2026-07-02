#!/bin/bash
# Run on VPS after: pip install -r requirements.txt
# Optional: export PLAYLIST_API_KEY=your-secret-key
exec uvicorn api:app --host 0.0.0.0 --port 8000
