# Sound Monitor — Changelog

## v2.3.0
- Reconnexion MQTT automatique : `reconnect_delay_set(5s→60s)` + callback `on_disconnect`
- Persistance de l'historique des alertes dans `/data/historique_{slug}.json` — survive aux redémarrages
- Timestamps des alertes en `dd/mm HH:MM` (plus de perte de contexte sur minuit)
- `historique` migré vers `collections.deque(maxlen=10)` — insert O(1)
- Dépendances Dockerfile épinglées : `numpy==1.26.4`, `paho-mqtt==2.1.0`, `requests==2.32.3`

## v2.2.1
- Sécurité : `run.sh` ne logue plus les credentials (ha_token, mqtt_password, RTSP URLs)
- Sécurité : `full_access: true` remplacé par `host_network: true` dans config.yaml
- Bug : `is_silence_mode()` mis en cache 30s — n'appelle plus l'API REST HA à chaque frame audio
- Bug : `proc.terminate()` suivi d'un `proc.wait(timeout=5)` pour éviter les processus ffmpeg zombies
- Bug : variable locale `warnings` renommée `soft_errors` (shadowing du module stdlib corrigé)
- Bug : `stderr=subprocess.DEVNULL` sur ffmpeg — pipe bloquant supprimé
- Bug : `retain=True` ajouté sur toutes les publications uptime (cohérence avec les autres sensors)
- Threading : watchdog fait un `join(timeout=1)` sur le thread mort avant restart
- Config : `ha_url` optionnel dans le schéma (utile si le hostname HA est non-standard)
- Client MQTT ID dynamique basé sur VERSION (plus de `v18` figé)
- `DeprecationWarning` supprimé uniquement pour le module `paho` (plus global)

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