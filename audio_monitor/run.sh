#!/bin/sh

echo "=== Diagnostic ==="
id
which ffmpeg && echo "ffmpeg OK" || echo "ffmpeg manquant"
echo "Options : $(python3 -c "import json; c=json.load(open('/data/options.json')); print(f'{len(c.get(\"sources\",[]))} source(s), mqtt={c.get(\"mqtt_host\",\"?\")}')" 2>/dev/null || echo 'non lisibles')"
echo "=================="

python3 /app/audio_monitor.py --config /data/options.json 2>&1