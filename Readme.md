# 🔊 Sound Monitor — Home Assistant Addon

Surveillance du niveau sonore en temps réel via des flux RTSP ou HTTP.  
Multi-sources, intégration native Home Assistant via MQTT Discovery.

---

## Fonctionnalités

- 📷 **Multi-sources** — surveille plusieurs caméras/micros en parallèle
- 📊 **5 sensors par source** — niveau instantané, moyen, pic, bruit de fond, historique alertes
- 🔔 **Détection intelligente** — seuil fixe + détection de variation brutale
- 🔇 **Mode silence** — désactive les alertes depuis HA sans redémarrer l'addon
- ⚖️ **Seuil dynamique** — modifiable depuis HA via `input_number` sans redémarrage
- 🔁 **Reconnexion automatique** — relance ffmpeg si le flux coupe
- 🐕 **Watchdog** — surveille les threads et les redémarre si nécessaire
- 🕐 **Calibration automatique** — mesure le bruit de fond au démarrage et recalibre périodiquement
- 📡 **MQTT Discovery** — entités créées automatiquement dans HA
- ⏱️ **Timestamp dans les logs** — logs horodatés pour faciliter le debug

---

## Prérequis

- Home Assistant OS ou Supervised
- Addon **Mosquitto broker** installé et configuré
- Une ou plusieurs caméras avec flux **RTSP** ou **HTTP/MJPEG**

---

## Installation

1. Dans Home Assistant, va dans **Paramètres → Modules complémentaires → Boutique**
2. Clique sur les **3 points** en haut à droite → **Dépôts**
3. Ajoute l'URL de ce repo : `https://github.com/kikkingoff/sound-monitor-addon`
4. Recherche **Sound Monitor** et installe-le

---

## Configuration

### Options principales

| Paramètre | Description | Exemple |
|---|---|---|
| `mqtt_host` | IP de ton broker MQTT | `192.168.1.30` |
| `mqtt_port` | Port MQTT | `1883` |
| `mqtt_user` | Username MQTT | `mqtt-user` |
| `mqtt_password` | Mot de passe MQTT | `password` |
| `ha_token` | Token longue durée HA (pour seuil dynamique) | `eyJ...` |
| `anti_spam_minutes` | Délai minimum entre deux alertes | `2` |
| `seuil_global` | Seuil global pour toutes les sources (0 = par source) | `0` |

### Configuration par source

```yaml
sources:
  - nom: "Entree"
    rtsp_url: "rtsp://admin:password@192.168.1.x:554//h264Preview_01_sub"
    seuil: 75
    variation_seuil: 15
    calibration_secs: 10
    recalibration_interval: 3600
    publish_interval: 5
```

| Paramètre | Description | Défaut |
|---|---|---|
| `nom` | Nom de la source (utilisé pour les entity_id) | — |
| `rtsp_url` | URL du flux RTSP ou HTTP | — |
| `seuil` | Niveau en dB déclenchant une alerte | `75` |
| `variation_seuil` | Variation brutale en dB déclenchant une alerte | `15` |
| `calibration_secs` | Durée de calibration au démarrage (secondes) | `10` |
| `recalibration_interval` | Intervalle de recalibration (secondes) | `3600` |
| `publish_interval` | Intervalle de publication moyen/pic (secondes) | `5` |

---

## Entités créées

Pour chaque source (exemple avec `nom: "Entree"`) :

| Entité | Description |
|---|---|
| `sensor.entree_niveau_sonore` | Niveau instantané (dB) |
| `sensor.entree_niveau_moyen` | Moyenne sur `publish_interval` secondes (dB) |
| `sensor.entree_niveau_pic` | Pic max sur `publish_interval` secondes (dB) |
| `sensor.entree_bruit_de_fond` | Bruit de fond calibré (dB) |
| `binary_sensor.entree_alerte_bruit` | Alerte ON/OFF |
| `sensor.entree_historique_alertes` | 10 dernières alertes |
| `binary_sensor.entree_connecte` | État de connexion au flux |
| `sensor.entree_uptime` | Durée de connexion (minutes) |

---

## Entités HA optionnelles

Ajoute dans `configuration.yaml` pour le seuil dynamique et le mode silence :

```yaml
input_boolean:
  sound_monitor_silence:
    name: "Mode Silence Son"
    icon: mdi:volume-off

input_number:
  sound_monitor_seuil_global:
    name: "Seuil Global Son"
    min: 0
    max: 100
    step: 1
    initial: 75
    unit_of_measurement: "dB"
    icon: mdi:volume-alert
```

Pour un seuil par source :
```yaml
input_number:
  seuil_entree:
    name: "Seuil Entrée"
    min: 40
    max: 100
    step: 1
    initial: 75
    unit_of_measurement: "dB"
```

> ⚠️ Le nom de l'entité doit correspondre au slug du nom de la source.
> Exemple : `nom: "Entree"` → `input_number.seuil_entree`
> Les caractères spéciaux et accents sont automatiquement convertis.

---

## Exemple d'automation

Analyse caméra + notification quand bruit détecté et absent :

```yaml
- alias: "Alerte bruit entrée"
  trigger:
    - platform: state
      entity_id: binary_sensor.entree_alerte_bruit
      to: "on"
  condition:
    - condition: state
      entity_id: device_tracker.mon_telephone
      state: "not_home"
  action:
    - service: notify.mobile_app
      data:
        title: "🔊 Bruit détecté"
        message: "Niveau : {{ states('sensor.entree_niveau_sonore') }}dB"
```

---

## Changelog

Voir [CHANGELOG.md](CHANGELOG.md)

---

## Licence

MIT — libre d'utilisation et de modification.