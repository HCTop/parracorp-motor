#!/bin/bash
# Start WhatsApp service (Node.js) in background
echo "[START] Iniciando wa_service.js..."
node wa_service.js &

# Wait for WA service to start
sleep 3

# Start Python Flask app with gunicorn
echo "[START] Iniciando bot.py con gunicorn..."
exec gunicorn bot:app --workers 1 --threads 4 --timeout 120 --bind 0.0.0.0:${PORT:-5000}
