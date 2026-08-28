"""Configuration for flo-x6-mqtt v2 (local OCPP bridge). All via env vars."""
import os


def _b(name, default):
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class Config:
    # --- OCPP server (the charger connects TO us) ---
    OCPP_HOST = os.getenv("FLO_OCPP_HOST", "0.0.0.0")
    OCPP_PORT = int(os.getenv("FLO_OCPP_PORT", "9000"))
    # Heartbeat interval (s) we hand the charger in BootNotification.
    HEARTBEAT_INTERVAL = int(os.getenv("FLO_HEARTBEAT_INTERVAL", "30"))

    # --- MQTT ---
    MQTT_HOST = os.getenv("FLO_MQTT_HOST", "192.168.1.100")
    MQTT_PORT = int(os.getenv("FLO_MQTT_PORT", "1883"))
    MQTT_USER = os.getenv("FLO_MQTT_USER", "")
    MQTT_PASS = os.getenv("FLO_MQTT_PASS", "")
    MQTT_PREFIX = os.getenv("FLO_MQTT_PREFIX", "flo-x6")          # base topic
    HA_DISCOVERY_PREFIX = os.getenv("FLO_HA_DISCOVERY_PREFIX", "homeassistant")

    # --- Device identity in HA (one device holds all entities) ---
    DEVICE_NAME = os.getenv("FLO_DEVICE_NAME", "Flo Home X6")
    DEVICE_ID = os.getenv("FLO_DEVICE_ID", "flo_x6")             # stable slug for entity ids

    # --- Behaviour ---
    # If true, log MQTT publishes instead of sending (used for offline sim tests).
    DRY_RUN = _b("FLO_DRY_RUN", False)
    LOG_LEVEL = os.getenv("FLO_LOG_LEVEL", "INFO").upper()
