#!/bin/sh

echo "=== Diagnostic ==="
id
which ffmpeg && echo "ffmpeg OK" || echo "ffmpeg manquant"
echo "Options : $(cat /data/options.json 2>/dev/null || echo 'non trouve')"
echo "=================="

python3 /app/audio_monitor.py --config /data/options.json 2>&1