FROM python:3.12-alpine

RUN apk add --no-cache \
    alsa-utils \
    alsa-lib \
    ffmpeg

RUN pip install --no-cache-dir numpy==1.26.4 paho-mqtt==2.1.0 requests==2.32.3

RUN mkdir -p /app

RUN addgroup -g 29 audiogrp 2>/dev/null || true && \
    addgroup root audiogrp 2>/dev/null || true

COPY run.sh /app/run.sh
COPY audio_monitor.py /app/audio_monitor.py

RUN chmod +x /app/run.sh

CMD ["/bin/sh", "/app/run.sh"]