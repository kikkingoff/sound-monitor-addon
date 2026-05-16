# Sound Monitor — Changelog

## v2.2.0
- Watchdog thread — redémarre automatiquement les sources mortes
- Sensor `binary_sensor.{slug}_connecte` — état connexion par source
- Sensor `sensor.{slug}_uptime` — uptime en minutes par source
- Notification MQTT reconnexion après coupure
- Mode silence global via `input_boolean.sound_monitor_silence`
- Seuil global optionnel via `input_number.sound_monitor_seuil_global`
- Validation de la config au démarrage
- Timestamp dans tous les logs
- Republication état au redémarrage HA (`homeassistant/status`)
- Log quand le seuil change depuis HA

## v2.1.0
- `object_id` forcé dans MQTT Discovery — plus de doublons dans les entity_id HA
- Device MQTT séparé par source
- Support flux HTTP/MJPEG en plus de RTSP

## v2.0.0
- Refactor complet multi-sources avec threads
- Chaque source génère ses propres entités MQTT

## v1.x
- Version mono-source initiale
- Lecture flux RTSP Reolink via ffmpeg
- Publication niveau sonore, alerte bruit, historique