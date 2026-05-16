#!/usr/bin/env python3
"""
audio_monitor.py v18 — Multi-sources
- Timestamp dans tous les logs
- Republication état au redémarrage HA
- Sensor état connexion par source
- Sensor uptime par source
- Notification MQTT reconnexion
- Watchdog thread
- Validation config au démarrage
- Mode silence global via input_boolean.sound_monitor_silence
- Seuil global ou par source
- CHANGELOG intégré
"""

VERSION = "2.2.0"

CHANGELOG = """
v2.2.0 — Watchdog, sensor connexion/uptime, mode silence, validation config
v2.1.0 — Multi-sources, object_id forcé, device par source
v2.0.0 — Refactor multi-sources avec threads
v1.x   — Version mono-source
"""

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
import argparse
import json
import time
import subprocess
import threading
import datetime
import requests
import numpy as np
import paho.mqtt.client as mqtt
import re
import sys

HA_URL       = "http://homeassistant.local:8123"
MAX_HISTO    = 10
ALERTE_TRIG  = 3
SILENCE_TRIG = 10
WATCHDOG_INT = 30   # secondes entre checks watchdog

_monitors    = []
_ha_token    = ""
_silence_entity = "input_boolean.sound_monitor_silence"


def log(source, msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{source}] {msg}", flush=True)


def slugify(nom):
    s = nom.lower().strip()
    s = re.sub(r"[àáâãäå]", "a", s)
    s = re.sub(r"[èéêë]", "e", s)
    s = re.sub(r"[ìíîï]", "i", s)
    s = re.sub(r"[òóôõö]", "o", s)
    s = re.sub(r"[ùúûü]", "u", s)
    s = re.sub(r"[^a-z0-9]", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def validate_config(config):
    """Valide la configuration avant démarrage."""
    errors = []

    required = ["mqtt_host", "mqtt_port", "sources"]
    for key in required:
        if key not in config:
            errors.append(f"Champ obligatoire manquant : {key}")

    sources = config.get("sources", [])
    if not sources:
        errors.append("Aucune source configurée")

    for i, src in enumerate(sources):
        if "nom" not in src:
            errors.append(f"Source {i+1} : champ 'nom' manquant")
        if "rtsp_url" not in src:
            errors.append(f"Source {i+1} : champ 'rtsp_url' manquant")
        url = src.get("rtsp_url", "")
        if url in ("", "rtsp://user:password@192.168.1.x:554//stream"):
            errors.append(f"Source {i+1} ({src.get('nom','?')}) : URL non configurée")
        if config.get("mqtt_host", "") in ("", "192.168.1.x"):
            errors.append("mqtt_host non configuré")
        if config.get("ha_token", "") in ("", "your_long_lived_token"):
            errors.append("ha_token non configuré — seuil HA et mode silence désactivés")

    return errors


def get_ha_state(entity, token):
    """Récupère l'état d'une entité HA."""
    if not token:
        return None
    try:
        resp = requests.get(
            f"{HA_URL}/api/states/{entity}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=3
        )
        if resp.status_code == 200:
            return resp.json().get("state")
    except Exception:
        pass
    return None


def is_silence_mode(token):
    """Vérifie si le mode silence est activé."""
    state = get_ha_state(_silence_entity, token)
    return state == "on"


class SourceMonitor:

    def __init__(self, config, mqtt_client, ha_token, anti_spam_minutes, seuil_global=None):
        self.nom                    = config["nom"]
        self.slug                   = slugify(self.nom)
        self.rtsp_url               = config["rtsp_url"]
        self.seuil_defaut           = seuil_global if seuil_global else config.get("seuil", 75)
        self.use_global_seuil       = seuil_global is not None
        self.variation_seuil        = config.get("variation_seuil", 15)
        self.calibration_secs       = config.get("calibration_secs", 10)
        self.recalibration_interval = config.get("recalibration_interval", 3600)
        self.publish_interval       = config.get("publish_interval", 5)
        self.mqtt                   = mqtt_client
        self.ha_token               = ha_token
        self.anti_spam_minutes      = anti_spam_minutes

        s = self.slug
        self.T_INST      = f"homeassistant/sensor/{s}/niveau_instant/state"
        self.T_MOY       = f"homeassistant/sensor/{s}/niveau_moyen/state"
        self.T_PIC       = f"homeassistant/sensor/{s}/niveau_pic/state"
        self.T_FOND      = f"homeassistant/sensor/{s}/niveau_fond/state"
        self.T_ALERTE    = f"homeassistant/binary_sensor/{s}/alerte/state"
        self.T_HISTO     = f"homeassistant/sensor/{s}/historique/state"
        self.T_CONNEXION = f"homeassistant/binary_sensor/{s}/connexion/state"
        self.T_UPTIME    = f"homeassistant/sensor/{s}/uptime/state"

        self.DEVICE = {
            "identifiers": [f"sound_monitor_{s}"],
            "name": self.nom,
            "model": f"Sound Monitor v{VERSION}",
            "manufacturer": "HA Addon"
        }

        self.alerte_active    = False
        self.alerte_count     = 0
        self.silence_count    = 0
        self.last_alerte_time = None
        self.historique       = []
        self.bruit_fond       = 0.0
        self.db_precedent     = 0.0
        self.seuil            = self.seuil_defaut
        self.seuil_entity     = f"input_number.seuil_{self.slug}"
        self._stop            = False
        self._connected       = False
        self._connect_time    = None
        self._thread          = None

    def setup_discovery(self):
        s = self.slug

        configs = [
            (f"homeassistant/sensor/{s}/niveau_instant/config", {
                "name": "Niveau Sonore",
                "object_id": f"{s}_niveau_sonore",
                "unique_id": f"{s}_niveau_instant",
                "state_topic": self.T_INST,
                "unit_of_measurement": "dB",
                "icon": "mdi:volume-high",
                "device": self.DEVICE
            }),
            (f"homeassistant/sensor/{s}/niveau_moyen/config", {
                "name": "Niveau Moyen",
                "object_id": f"{s}_niveau_moyen",
                "unique_id": f"{s}_niveau_moyen",
                "state_topic": self.T_MOY,
                "unit_of_measurement": "dB",
                "icon": "mdi:volume-medium",
                "device": self.DEVICE
            }),
            (f"homeassistant/sensor/{s}/niveau_pic/config", {
                "name": "Niveau Pic",
                "object_id": f"{s}_niveau_pic",
                "unique_id": f"{s}_niveau_pic",
                "state_topic": self.T_PIC,
                "unit_of_measurement": "dB",
                "icon": "mdi:volume-high",
                "device": self.DEVICE
            }),
            (f"homeassistant/sensor/{s}/niveau_fond/config", {
                "name": "Bruit de Fond",
                "object_id": f"{s}_bruit_de_fond",
                "unique_id": f"{s}_niveau_fond",
                "state_topic": self.T_FOND,
                "unit_of_measurement": "dB",
                "icon": "mdi:volume-off",
                "device": self.DEVICE
            }),
            (f"homeassistant/binary_sensor/{s}/alerte/config", {
                "name": "Alerte Bruit",
                "object_id": f"{s}_alerte_bruit",
                "unique_id": f"{s}_alerte",
                "state_topic": self.T_ALERTE,
                "payload_on": "ON",
                "payload_off": "OFF",
                "device_class": "sound",
                "icon": "mdi:volume-alert",
                "device": self.DEVICE
            }),
            (f"homeassistant/sensor/{s}/historique/config", {
                "name": "Historique Alertes",
                "object_id": f"{s}_historique_alertes",
                "unique_id": f"{s}_historique",
                "state_topic": self.T_HISTO,
                "icon": "mdi:history",
                "device": self.DEVICE
            }),
            (f"homeassistant/binary_sensor/{s}/connexion/config", {
                "name": "Connecté",
                "object_id": f"{s}_connecte",
                "unique_id": f"{s}_connexion",
                "state_topic": self.T_CONNEXION,
                "payload_on": "ON",
                "payload_off": "OFF",
                "device_class": "connectivity",
                "icon": "mdi:lan-connect",
                "device": self.DEVICE
            }),
            (f"homeassistant/sensor/{s}/uptime/config", {
                "name": "Uptime",
                "object_id": f"{s}_uptime",
                "unique_id": f"{s}_uptime",
                "state_topic": self.T_UPTIME,
                "unit_of_measurement": "min",
                "icon": "mdi:timer",
                "device": self.DEVICE
            }),
        ]

        for topic, payload in configs:
            self.mqtt.publish(topic, json.dumps(payload), retain=True)

        time.sleep(0.5)
        self.publish_state()
        log(self.nom, f"Discovery publiée — entity prefix: {s}_*")

    def publish_state(self):
        """Publie l'état courant — au démarrage et au redémarrage HA."""
        self.mqtt.publish(self.T_ALERTE,    "ON" if self.alerte_active else "OFF", retain=True)
        self.mqtt.publish(self.T_HISTO,     " | ".join(self.historique) if self.historique else "Aucune alerte", retain=True)
        self.mqtt.publish(self.T_FOND,      str(self.bruit_fond), retain=True)
        self.mqtt.publish(self.T_CONNEXION, "ON" if self._connected else "OFF", retain=True)
        if self._connect_time:
            uptime = int((datetime.datetime.now() - self._connect_time).total_seconds() / 60)
            self.mqtt.publish(self.T_UPTIME, str(uptime))

    def set_connected(self, connected):
        """Met à jour l'état de connexion."""
        was_connected = self._connected
        self._connected = connected
        if connected and not was_connected:
            self._connect_time = datetime.datetime.now()
            self.mqtt.publish(self.T_CONNEXION, "ON", retain=True)
            log(self.nom, "Connexion établie")
        elif not connected and was_connected:
            self._connect_time = None
            self.mqtt.publish(self.T_CONNEXION, "OFF", retain=True)
            self.mqtt.publish(self.T_UPTIME, "0")
            log(self.nom, "Connexion perdue")

    def get_seuil_ha(self):
        if self.use_global_seuil:
            val = get_ha_state("input_number.sound_monitor_seuil_global", self.ha_token)
        else:
            val = get_ha_state(self.seuil_entity, self.ha_token)
        if val and val not in ("unknown", "unavailable"):
            try:
                return int(float(val))
            except Exception:
                pass
        return self.seuil_defaut

    def rms_to_db(self, rms):
        if rms < 1.0:
            return 0.0
        return round(float(20 * np.log10(rms)), 1)

    def start_ffmpeg(self):
        if self.rtsp_url.startswith("rtsp://"):
            cmd = [
                "ffmpeg", "-rtsp_transport", "tcp",
                "-i", self.rtsp_url,
                "-vn", "-ar", "16000", "-ac", "1",
                "-f", "s16le", "-loglevel", "error",
                "pipe:1"
            ]
        else:
            cmd = [
                "ffmpeg",
                "-i", self.rtsp_url,
                "-vn", "-ar", "16000", "-ac", "1",
                "-f", "s16le", "-loglevel", "error",
                "pipe:1"
            ]
        log(self.nom, f"Commande : {' '.join(cmd[:4])}...")
        return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def calibrate(self, proc):
        log(self.nom, f"Calibration {self.calibration_secs}s...")
        buf = []
        t0  = time.time()
        while time.time() - t0 < self.calibration_secs:
            data = proc.stdout.read(2048)
            if not data:
                break
            samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
            buf.append(self.rms_to_db(np.sqrt(np.mean(samples ** 2))))
        if buf:
            self.bruit_fond = round(float(np.mean(buf)), 1)
            self.mqtt.publish(self.T_FOND, str(self.bruit_fond), retain=True)
            log(self.nom, f"Bruit de fond : {self.bruit_fond}dB")

    def run(self):
        reconnect_count = 0
        while not self._stop:
            log(self.nom, "Connexion RTSP...")
            try:
                proc = self.start_ffmpeg()
            except Exception as e:
                log(self.nom, f"Erreur ffmpeg : {e} — retry 30s")
                self.set_connected(False)
                time.sleep(30)
                continue

            time.sleep(3)
            if proc.poll() is not None:
                err = proc.stderr.read().decode()
                log(self.nom, f"ffmpeg mort : {err[:150]} — retry 30s")
                self.set_connected(False)
                time.sleep(30)
                continue

            self.set_connected(True)
            if reconnect_count > 0:
                log(self.nom, f"Reconnexion #{reconnect_count} réussie")
            reconnect_count += 1

            self.calibrate(proc)
            self.seuil        = self.get_seuil_ha()
            last_calibration  = time.time()
            last_publish      = 0
            last_instant      = 0
            last_uptime       = 0
            seuil_refresh     = 0
            niveau_buffer     = []

            log(self.nom, f"Surveillance active — seuil {self.seuil}dB")

            try:
                while not self._stop:
                    data = proc.stdout.read(2048)
                    if not data or proc.poll() is not None:
                        log(self.nom, "Flux interrompu — reconnexion 10s")
                        self.set_connected(False)
                        break

                    samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                    db = self.rms_to_db(np.sqrt(np.mean(samples ** 2)))
                    niveau_buffer.append(db)
                    now = time.time()

                    # Niveau instantané
                    if now - last_instant >= 1:
                        self.mqtt.publish(self.T_INST, str(db))
                        last_instant = now

                    # Uptime toutes les minutes
                    if now - last_uptime >= 60 and self._connect_time:
                        uptime = int((datetime.datetime.now() - self._connect_time).total_seconds() / 60)
                        self.mqtt.publish(self.T_UPTIME, str(uptime))
                        last_uptime = now

                    # Refresh seuil HA
                    if now - seuil_refresh >= 60:
                        old_seuil = self.seuil
                        self.seuil = self.get_seuil_ha()
                        if self.seuil != old_seuil:
                            log(self.nom, f"Seuil mis à jour : {old_seuil}dB → {self.seuil}dB")
                        seuil_refresh = now

                    # Recalibration
                    if now - last_calibration >= self.recalibration_interval:
                        self.calibrate(proc)
                        last_calibration = now

                    # Mode silence — ignore les alertes
                    if is_silence_mode(self.ha_token):
                        self.alerte_count = 0
                        self.silence_count += 1
                        if self.alerte_active and self.silence_count >= SILENCE_TRIG:
                            self.alerte_active = False
                            self.mqtt.publish(self.T_ALERTE, "OFF")
                        if now - last_publish >= self.publish_interval:
                            if niveau_buffer:
                                moy = round(float(np.mean(niveau_buffer)), 1)
                                pic = round(float(max(niveau_buffer)), 1)
                                self.mqtt.publish(self.T_MOY, str(moy))
                                self.mqtt.publish(self.T_PIC, str(pic))
                                niveau_buffer = []
                            last_publish = now
                        continue

                    # Détection
                    variation = db - self.db_precedent
                    depasse   = db >= self.seuil
                    varie     = variation >= self.variation_seuil and db > self.bruit_fond + 10
                    self.db_precedent = db

                    if depasse or varie:
                        self.alerte_count += 1
                        self.silence_count = 0
                    else:
                        self.silence_count += 1
                        self.alerte_count = 0

                    # Anti-spam
                    anti_spam_ok = True
                    if self.last_alerte_time:
                        elapsed = (datetime.datetime.now() - self.last_alerte_time).total_seconds()
                        anti_spam_ok = elapsed >= self.anti_spam_minutes * 60

                    # Déclenchement alerte
                    if not self.alerte_active and self.alerte_count >= ALERTE_TRIG and anti_spam_ok:
                        self.alerte_active = True
                        self.last_alerte_time = datetime.datetime.now()
                        self.mqtt.publish(self.T_ALERTE, "ON")
                        raison = f"seuil ({db:.1f}dB)" if depasse else f"variation (+{variation:.1f}dB)"
                        log(self.nom, f"ALERTE — {db:.1f}dB ({raison})")
                        ts_str = datetime.datetime.now().strftime("%H:%M")
                        self.historique.insert(0, f"{ts_str} {db:.1f}dB ({raison})")
                        if len(self.historique) > MAX_HISTO:
                            self.historique.pop()
                        self.mqtt.publish(self.T_HISTO, " | ".join(self.historique))

                    # Désactivation alerte
                    if self.alerte_active and self.silence_count >= SILENCE_TRIG:
                        self.alerte_active = False
                        self.mqtt.publish(self.T_ALERTE, "OFF")
                        log(self.nom, "Alerte levée")

                    # Publication moyen + pic
                    if now - last_publish >= self.publish_interval:
                        if niveau_buffer:
                            moy = round(float(np.mean(niveau_buffer)), 1)
                            pic = round(float(max(niveau_buffer)), 1)
                            self.mqtt.publish(self.T_MOY, str(moy))
                            self.mqtt.publish(self.T_PIC, str(pic))
                            log(self.nom, f"Moy:{moy}dB Pic:{pic}dB Fond:{self.bruit_fond}dB Seuil:{self.seuil}dB")
                            niveau_buffer = []
                        last_publish = now

            except Exception as e:
                log(self.nom, f"Erreur boucle : {e}")
                self.set_connected(False)

            try:
                proc.terminate()
            except Exception:
                pass
            if not self._stop:
                time.sleep(10)

        log(self.nom, "Arrêté")

    def start(self):
        self._thread = threading.Thread(target=self.run, daemon=True, name=f"mon_{self.slug}")
        self._thread.start()

    def stop(self):
        self._stop = True

    def is_alive(self):
        return self._thread is not None and self._thread.is_alive()


def watchdog(monitors):
    """Surveille les threads et les redémarre si morts."""
    log("WATCHDOG", "Démarré")
    while True:
        time.sleep(WATCHDOG_INT)
        for mon in monitors:
            if not mon.is_alive() and not mon._stop:
                log("WATCHDOG", f"Thread {mon.nom} mort — redémarrage")
                mon._stop = False
                mon.start()


def on_mqtt_message(client, userdata, msg):
    """Republication de l'état au redémarrage de HA."""
    try:
        payload = msg.payload.decode()
        if msg.topic == "homeassistant/status" and payload == "online":
            log("MQTT", "HA redémarré — republication de l'état")
            for mon in _monitors:
                mon.publish_state()
    except Exception as e:
        log("MQTT", f"Erreur callback : {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/data/options.json")
    args = parser.parse_args()

    log("MAIN", f"Sound Monitor v{VERSION} démarrage")

    # Charge la config
    try:
        with open(args.config) as f:
            config = json.load(f)
    except Exception as e:
        log("MAIN", f"Erreur lecture config : {e}")
        sys.exit(1)

    # Validation
    errors = validate_config(config)
    warnings = [e for e in errors if "désactivés" in e]
    critiques = [e for e in errors if "désactivés" not in e]

    for w in warnings:
        log("CONFIG", f"⚠️  {w}")
    for e in critiques:
        log("CONFIG", f"❌ {e}")
    if critiques:
        log("MAIN", "Erreurs critiques — arrêt")
        sys.exit(1)

    global _ha_token
    _ha_token     = config.get("ha_token", "")
    mqtt_host     = config.get("mqtt_host")
    mqtt_port     = config.get("mqtt_port", 1883)
    mqtt_user     = config.get("mqtt_user", "")
    mqtt_password = config.get("mqtt_password", "")
    anti_spam     = config.get("anti_spam_minutes", 2)
    seuil_global_val = config.get("seuil_global", 0)
    seuil_global = seuil_global_val if seuil_global_val > 0 else None
    sources       = config.get("sources", [])

    log("MAIN", f"{len(sources)} source(s) configurée(s)")

    # Connexion MQTT
    client = mqtt.Client(client_id="sound_monitor_v18")
    if mqtt_user:
        client.username_pw_set(mqtt_user, mqtt_password)
    client.on_message = on_mqtt_message

    try:
        client.connect(mqtt_host, mqtt_port, keepalive=60)
        client.subscribe("homeassistant/status")
        client.loop_start()
        log("MAIN", f"MQTT connecté à {mqtt_host}:{mqtt_port}")
    except Exception as e:
        log("MAIN", f"Erreur MQTT : {e}")
        sys.exit(1)

    # Démarre les monitors
    for src in sources:
        mon = SourceMonitor(src, client, _ha_token, anti_spam, seuil_global)
        mon.setup_discovery()
        mon.start()
        _monitors.append(mon)
        log("MAIN", f"Source démarrée : {src['nom']}")

    # Watchdog
    wd = threading.Thread(target=watchdog, args=(_monitors,), daemon=True, name="watchdog")
    wd.start()

    log("MAIN", "Toutes les sources actives — surveillance en cours")

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        log("MAIN", "Arrêt demandé")
        for mon in _monitors:
            mon.stop()
            client.publish(mon.T_ALERTE,    "OFF")
            client.publish(mon.T_CONNEXION, "OFF")
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()