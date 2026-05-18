"""
flo-x6-mqtt — Daemon bridge Flo X6 → MQTT → Home Assistant
Polling adaptatif, gestion complète de la disponibilité, MQTT Discovery automatique.
"""

import json
import logging
import os
import signal
import sys

def _load_dotenv(path=".env"):
    """Charge les variables d'environnement depuis un fichier .env sans passer par bash."""
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

_load_dotenv()
import time

import paho.mqtt.client as mqtt

from flo_client.auth import get_valid_access_token, load_tokens, save_tokens, refresh_access_token
from flo_client.client import FloX6Client
from flo_client.connectivity import check_internet, check_flo_api
from flo_client.exceptions import FloAuthError, FloNetworkError, FloAPIError

# ─────────────────────────────────────────────────────────────
# Configuration — variables d'environnement
# ─────────────────────────────────────────────────────────────
FLO_USERNAME   = os.environ.get("FLO_USERNAME", "")
FLO_PASSWORD   = os.environ.get("FLO_PASSWORD", "")

MQTT_HOST      = os.environ.get("HASS_MQTT_HOST", "192.168.10.100")
MQTT_PORT      = int(os.environ.get("HASS_MQTT_PORT", "1883"))
MQTT_USER      = os.environ.get("HASS_MQTT_USERNAME", "")
MQTT_PASS      = os.environ.get("HASS_MQTT_PASSWORD", "")

# Intervalles de polling adaptatifs (secondes)
POLL_CHARGING  = int(os.environ.get("POLL_INTERVAL_CHARGING",  "30"))
POLL_PLUGGED   = int(os.environ.get("POLL_INTERVAL_PLUGGED",   "60"))
POLL_AVAILABLE = int(os.environ.get("POLL_INTERVAL_AVAILABLE", "120"))
POLL_RETRY     = int(os.environ.get("POLL_INTERVAL_RETRY",     "60"))

API_TIMEOUT    = int(os.environ.get("API_TIMEOUT",             "10"))
ERROR_THRESHOLD = int(os.environ.get("CONSECUTIVE_ERRORS_THRESHOLD", "3"))
LOG_LEVEL      = os.environ.get("LOG_LEVEL", "INFO").upper()

# ─────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s : %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("flo_x6_mqtt")

# ─────────────────────────────────────────────────────────────
# État global du daemon
# ─────────────────────────────────────────────────────────────
state = {
    # Borne
    "station_uid":       None,
    "evse_status":       "Unknown",
    "connection_status": "Unknown",

    # Session
    "session_id":        None,
    "session_id_prev":   None,
    "energy_wh":         0.0,

    # Disponibilité
    "bridge_online":     False,
    "internet_ok":       False,
    "flo_cloud_ok":      False,
    "consecutive_errors": 0,
    "last_success_ts":   None,
    "last_error_cause":  "",

    # Contrôle commandes
    "command_lock":      False,
    "command_lock_until": 0,

    # Drapeau reconnexion MQTT — déclenche republication complète (False au démarrage)
    "mqtt_reconnected":  False,
    "mqtt_first_connect": True,  # True = connexion initiale, pas une reconnexion
}

# ─────────────────────────────────────────────────────────────
# Topics MQTT
# ─────────────────────────────────────────────────────────────
def topics(uid: str) -> dict:
    base = f"flo/{uid}"
    return {
        "availability":   f"{base}/availability",
        "command_charge": f"{base}/switch/charge/command",
        "state_charge":   f"{base}/switch/charge/state",
        # Sensors
        "evse_status":        f"{base}/sensor/evse_status/state",
        "amperage":           f"{base}/sensor/amperage/state",
        "amperage_offer":     f"{base}/sensor/amperage_offer/state",
        "voltage":            f"{base}/sensor/voltage/state",
        "power":              f"{base}/sensor/power/state",
        "energy_session":     f"{base}/sensor/energy_session/state",
        "session_duration":   f"{base}/sensor/session_duration/state",
        "session_cost":       f"{base}/sensor/session_cost/state",
        "session_state":      f"{base}/sensor/session_state/state",
        "firmware":           f"{base}/sensor/firmware/state",
        "max_amperage":       f"{base}/sensor/max_amperage/state",
        "schedule_kind":      f"{base}/sensor/schedule_kind/state",
        # Binary sensors
        "bs_connected":   f"{base}/binary_sensor/connected/state",
        "bs_plugged":     f"{base}/binary_sensor/plugged/state",
        "bs_charging":    f"{base}/binary_sensor/charging/state",
        "bs_error":       f"{base}/binary_sensor/error/state",
        "bs_session":     f"{base}/binary_sensor/session_active/state",
        "bs_schedule":    f"{base}/binary_sensor/schedule_enabled/state",
        # Diagnostic bridge
        "diag_internet":  f"{base}/binary_sensor/internet/state",
        "diag_cloud":     f"{base}/binary_sensor/flo_cloud/state",
        "diag_last_ok":   f"{base}/sensor/last_update/state",
        "diag_error":     f"{base}/sensor/last_error/state",
        "diag_err_count": f"{base}/sensor/error_count/state",
    }

T = {}  # sera initialisé après découverte du UID

# ─────────────────────────────────────────────────────────────
# MQTT Discovery — construit les configs pour Home Assistant
# ─────────────────────────────────────────────────────────────
def device_info(station: dict) -> dict:
    return {
        "identifiers":    [f"flo_x6_{station['chargingStationUid']}"],
        "name":           station.get("stationPreferences", {}).get("nickname") or "Flo Home X6",
        "manufacturer":   station.get("vendor", "flo").capitalize(),
        "model":          station.get("model", "FLO Home X6"),
        "sw_version":     station.get("firmwareVersion", ""),
    }

def discovery_sensor(uid, name, friendly, device, unit=None, device_class=None,
                     state_class=None, entity_category=None, icon=None) -> tuple:
    obj_id = f"flo_{uid}_{name}"
    payload = {
        "unique_id":           obj_id,
        "name":                friendly,
        "state_topic":         T[f"sensor_{name}" if f"sensor_{name}" in T else name],
        "availability_topic":  T["availability"],
        "payload_available":   "online",
        "payload_not_available": "offline",
        "device":              device,
    }
    if unit:          payload["unit_of_measurement"] = unit
    if device_class:  payload["device_class"]        = device_class
    if state_class:   payload["state_class"]         = state_class
    if entity_category: payload["entity_category"]   = entity_category
    if icon:          payload["icon"]                = icon
    topic = f"homeassistant/sensor/{obj_id}/config"
    return topic, payload

def discovery_binary(uid, name, friendly, device, device_class=None,
                     entity_category=None, icon=None) -> tuple:
    obj_id = f"flo_{uid}_{name}"
    payload = {
        "unique_id":             obj_id,
        "name":                  friendly,
        "state_topic":           T[f"bs_{name}"] if f"bs_{name}" in T else T[f"diag_{name}"],
        "payload_on":            "ON",
        "payload_off":           "OFF",
        "availability_topic":    T["availability"],
        "payload_available":     "online",
        "payload_not_available": "offline",
        "device":                device,
    }
    if device_class:    payload["device_class"]   = device_class
    if entity_category: payload["entity_category"] = entity_category
    if icon:            payload["icon"]            = icon
    topic = f"homeassistant/binary_sensor/{obj_id}/config"
    return topic, payload

def publish_discovery(mqttc: mqtt.Client, station: dict):
    uid = station["chargingStationUid"]
    dev = device_info(station)

    configs = []

    # Switch charge on/off
    obj_id = f"flo_{uid}_charge"
    configs.append((
        f"homeassistant/switch/{obj_id}/config",
        {
            "unique_id":             obj_id,
            "name":                  "Charge",
            "state_topic":           T["state_charge"],
            "command_topic":         T["command_charge"],
            "payload_on":            "START",
            "payload_off":           "STOP",
            "state_on":              "ON",
            "state_off":             "OFF",
            "availability_topic":    T["availability"],
            "payload_available":     "online",
            "payload_not_available": "offline",
            "icon":                  "mdi:ev-station",
            "device":                dev,
        }
    ))

    # Sensors — borne
    sensors = [
        ("evse_status",      "EVSE Status",           None,   None,        None,               None,            "mdi:ev-plug-type1"),
        ("amperage",         "Current",               "A",    "current",   "measurement",      None,            None),
        ("amperage_offer",   "Current Offered",       "A",    "current",   "measurement",      None,            "mdi:current-ac"),
        ("voltage",          "Voltage",               "V",    "voltage",   "measurement",      None,            None),
        ("power",            "Power",                 "W",    "power",     "measurement",      None,            None),
        ("energy_session",   "Session Energy",        "kWh",  "energy",    "total_increasing", None,            None),
        ("session_duration", "Session Duration",      "min",  "duration",  "measurement",      None,            "mdi:timer"),
        ("session_cost",     "Session Cost",          "$",    "monetary",  "total_increasing", None,            "mdi:currency-usd"),
        ("session_state",    "Session State",         None,   None,        None,               None,            "mdi:information"),
        ("firmware",         "Firmware",              None,   None,        None,               "diagnostic",    "mdi:chip"),
        ("max_amperage",     "Max Amperage",          "A",    "current",   None,               "diagnostic",    None),
        ("schedule_kind",    "Schedule Mode",         None,   None,        None,               "diagnostic",    "mdi:calendar"),
    ]

    for name, friendly, unit, dc, sc, category, icon in sensors:
        obj_id = f"flo_{uid}_{name}"
        payload = {
            "unique_id":             obj_id,
            "name":                  friendly,
            "state_topic":           T[name],
            "availability_topic":    T["availability"],
            "payload_available":     "online",
            "payload_not_available": "offline",
            "device":                dev,
        }
        if unit:     payload["unit_of_measurement"] = unit
        if dc:       payload["device_class"]        = dc
        if sc:       payload["state_class"]         = sc
        if category: payload["entity_category"]     = category
        if icon:     payload["icon"]                = icon
        configs.append((f"homeassistant/sensor/{obj_id}/config", payload))

    # Binary sensors — borne
    binary_sensors = [
        ("connected", "Connected",        "connectivity",    None,         "mdi:cloud-check"),
        ("plugged",   "Cable Plugged",    "plug",            None,         "mdi:ev-plug-type1"),
        ("charging",  "Charging",         "battery_charging", None,        None),
        ("error",     "Error",            "problem",         None,         None),
        ("session",   "Session Active",   "running",         None,         "mdi:lightning-bolt"),
        ("schedule",  "Schedule Active",  None,              None,         "mdi:calendar-clock"),
    ]

    bs_topic_map = {
        "connected": T["bs_connected"],
        "plugged":   T["bs_plugged"],
        "charging":  T["bs_charging"],
        "error":     T["bs_error"],
        "session":   T["bs_session"],
        "schedule":  T["bs_schedule"],
    }

    for name, friendly, dc, category, icon in binary_sensors:
        obj_id = f"flo_{uid}_{name}"
        payload = {
            "unique_id":             obj_id,
            "name":                  friendly,
            "state_topic":           bs_topic_map[name],
            "payload_on":            "ON",
            "payload_off":           "OFF",
            "availability_topic":    T["availability"],
            "payload_available":     "online",
            "payload_not_available": "offline",
            "device":                dev,
        }
        if dc:       payload["device_class"]    = dc
        if category: payload["entity_category"] = category
        if icon:     payload["icon"]            = icon
        configs.append((f"homeassistant/binary_sensor/{obj_id}/config", payload))

    # Entités de diagnostic du bridge
    diag_dev = {**dev, "name": dev["name"] + " Bridge"}

    diag_binary = [
        ("internet", T["diag_internet"], "Internet",      "connectivity", "diagnostic"),
        ("cloud",    T["diag_cloud"],    "Flo Cloud",     "connectivity", "diagnostic"),
    ]
    for name, topic, friendly, dc, category in diag_binary:
        obj_id = f"flo_{uid}_bridge_{name}"
        configs.append((f"homeassistant/binary_sensor/{obj_id}/config", {
            "unique_id":       obj_id,
            "name":            friendly,
            "state_topic":     topic,
            "payload_on":      "ON",
            "payload_off":     "OFF",
            "device_class":    dc,
            "entity_category": category,
            "device":          diag_dev,
        }))

    diag_sensors = [
        ("last_update",  T["diag_last_ok"],   "Last Update",         "timestamp", None,          "diagnostic"),
        ("last_error",   T["diag_error"],     "Last Error",          None,        None,           "diagnostic"),
        ("error_count",  T["diag_err_count"], "Consecutive Errors",  None,        "measurement",  "diagnostic"),
    ]
    for name, topic, friendly, dc, sc, category in diag_sensors:
        obj_id = f"flo_{uid}_bridge_{name}"
        payload = {
            "unique_id":       obj_id,
            "name":            friendly,
            "state_topic":     topic,
            "entity_category": category,
            "device":          diag_dev,
        }
        if dc: payload["device_class"] = dc
        if sc: payload["state_class"]  = sc
        configs.append((f"homeassistant/sensor/{obj_id}/config", payload))

    # Publier tout avec retain=True
    for topic, payload in configs:
        mqttc.publish(topic, json.dumps(payload), retain=True, qos=1)
    log.info("Discovery publiée : %d entités.", len(configs))

# ─────────────────────────────────────────────────────────────
# Publication de l'état
# ─────────────────────────────────────────────────────────────
def pub(mqttc: mqtt.Client, topic: str, value, retain=False):
    mqttc.publish(topic, str(value), retain=retain, qos=1)

def publish_state(mqttc: mqtt.Client, station: dict, session):
    evse    = station.get("evse", {})
    evse_st = evse.get("status", "Unknown")
    prefs   = station.get("stationPreferences", {})
    conns   = evse.get("connectors", [])
    sched   = station.get("schedule", {})

    # --- Sensors borne ---
    pub(mqttc, T["evse_status"],   evse_st)
    pub(mqttc, T["firmware"],      station.get("firmwareVersion", ""))
    pub(mqttc, T["max_amperage"],  conns[0].get("maxAmperage", 0) if conns else 0)
    pub(mqttc, T["schedule_kind"], sched.get("kind", "unknown"))

    # --- Binary sensors borne ---
    pub(mqttc, T["bs_connected"], "ON" if station.get("connectionStatus") == "Online" else "OFF")
    pub(mqttc, T["bs_plugged"],   "ON" if evse_st in ("PluggedIn", "Charging", "Reserved") else "OFF")
    pub(mqttc, T["bs_charging"],  "ON" if evse_st == "Charging" else "OFF")
    pub(mqttc, T["bs_error"],     "ON" if evse_st in ("Inoperative", "OutOfOrder") else "OFF")
    pub(mqttc, T["bs_schedule"],  "ON" if sched.get("isEnabled") else "OFF")

    # Switch état charge
    pub(mqttc, T["state_charge"],
        "ON" if evse_st == "Charging" else "OFF", retain=True)

    # --- Session ---
    if session:
        sid = session.get("id")

        # Détection reset kWh (nouvelle session)
        energy_wh = session.get("energyTransferredWh", 0.0)
        if sid != state.get("session_id_prev"):
            state["session_id_prev"] = sid
            log.info("Nouvelle session détectée (%s) — compteur énergie remis à 0.", sid)

        amp     = session.get("amperage", 0.0)
        voltage = session.get("voltage", 0.0)
        dur_ms  = session.get("durationMs", 0)
        cost    = session.get("cost", {})

        pub(mqttc, T["amperage"],         round(amp, 1))
        pub(mqttc, T["amperage_offer"],   round(session.get("amperageOffer", 0), 1))
        pub(mqttc, T["voltage"],          round(voltage, 1))
        pub(mqttc, T["power"],            round(amp * voltage, 0))
        pub(mqttc, T["energy_session"],   round(energy_wh / 1000, 3))
        pub(mqttc, T["session_duration"], round(dur_ms / 60000, 1))
        pub(mqttc, T["session_cost"],     round(cost.get("estimatedCost", 0), 4))
        pub(mqttc, T["session_state"],    session.get("sessionState", "Unknown"))
        pub(mqttc, T["bs_session"],       "ON")
    else:
        # Pas de session active — valeurs à zéro
        pub(mqttc, T["amperage"],         0)
        pub(mqttc, T["amperage_offer"],   0)
        pub(mqttc, T["voltage"],          0)
        pub(mqttc, T["power"],            0)
        pub(mqttc, T["energy_session"],   0)
        pub(mqttc, T["session_duration"], 0)
        pub(mqttc, T["session_cost"],     0)
        pub(mqttc, T["session_state"],    "Idle")
        pub(mqttc, T["bs_session"],       "OFF")

def publish_diagnostic(mqttc: mqtt.Client):
    pub(mqttc, T["diag_internet"],  "ON" if state["internet_ok"]   else "OFF")
    pub(mqttc, T["diag_cloud"],     "ON" if state["flo_cloud_ok"]  else "OFF")
    pub(mqttc, T["diag_err_count"], state["consecutive_errors"])
    pub(mqttc, T["diag_error"],     state["last_error_cause"] or "")
    if state["last_success_ts"]:
        pub(mqttc, T["diag_last_ok"],
            time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(state["last_success_ts"])))

def set_availability(mqttc: mqtt.Client, available: bool, cause: str = ""):
    was_online = state["bridge_online"]
    state["bridge_online"] = available

    if available:
        mqttc.publish(T["availability"], "online",  retain=True, qos=1)
        if not was_online:
            log.info("Bridge en ligne.")
    else:
        mqttc.publish(T["availability"], "offline", retain=True, qos=1)
        if cause:
            state["last_error_cause"] = cause
        if was_online:
            log.error("Bridge hors ligne : %s", cause)

# ─────────────────────────────────────────────────────────────
# Gestion des commandes depuis Home Assistant
# ─────────────────────────────────────────────────────────────
def on_command(mqttc, userdata, msg):
    payload = msg.payload.decode("utf-8").strip().upper()
    uid     = state.get("station_uid")
    log.info("Commande MQTT reçue : '%s'", payload)

    if payload not in ("START", "STOP"):
        log.warning("Commande inconnue ignorée : '%s'", payload)
        return

    if not state["bridge_online"]:
        log.warning("Commande ignorée — bridge hors ligne.")
        return

    # Guard : bloquer les commandes pendant une transition
    if time.time() < state["command_lock_until"]:
        remaining = state["command_lock_until"] - time.time()
        log.warning("Commande ignorée — transition en cours (encore %.0fs).", remaining)
        return

    if not uid:
        log.error("Commande ignorée — UID borne non disponible.")
        return

    tokens = load_tokens()
    if not tokens:
        log.error("Commande ignorée — pas de token disponible.")
        return

    client = FloX6Client(tokens["access_token"], timeout=API_TIMEOUT)

    if payload == "START":
        log.info("Démarrage de la charge...")
        ok = client.start_charge(uid, evse_id="1")
        if ok:
            # Verrouiller 40s : start prend jusqu'à 16s + marge
            state["command_lock_until"] = time.time() + 40
            log.info("start_charge accepté. Verrou 40s.")
        else:
            log.error("start_charge échoué.")

    elif payload == "STOP":
        log.info("Arrêt de la charge...")
        ok = client.stop_charge(uid)
        if ok:
            # Verrouiller 30s : stop prend ~5s, mais on bloque start 30s (sécurité)
            state["command_lock_until"] = time.time() + 30
            log.info("stop_charge accepté. Verrou 30s.")
        else:
            log.error("stop_charge échoué.")

# ─────────────────────────────────────────────────────────────
# Callbacks MQTT
# ─────────────────────────────────────────────────────────────
def on_connect(mqttc, userdata, connect_flags, reason_code, properties):
    if reason_code == 0:
        log.info("Connecté au broker MQTT %s:%s", MQTT_HOST, MQTT_PORT)
        if state.get("station_uid"):
            mqttc.subscribe(T["command_charge"], qos=1)
            log.info("Abonné à %s", T["command_charge"])
            # Republier availability immédiatement sans attendre le prochain poll
            if state.get("bridge_online"):
                mqttc.publish(T["availability"], "online", retain=True, qos=1)
                log.info("Availability 'online' republié immédiatement.")
        # Signaler à la boucle principale qu'une republication discovery est nécessaire
        # (seulement sur reconnexion, pas sur la connexion initiale)
        if state["mqtt_first_connect"]:
            state["mqtt_first_connect"] = False
        else:
            state["mqtt_reconnected"] = True
    else:
        log.error("Connexion MQTT refusée : code %s", reason_code)

def on_disconnect(mqttc, userdata, disconnect_flags, reason_code, properties):
    if reason_code != 0:
        log.warning("Déconnecté du broker MQTT (code %s) — reconnexion auto...", reason_code)

def on_message(mqttc, userdata, msg):
    on_command(mqttc, userdata, msg)

# ─────────────────────────────────────────────────────────────
# Setup MQTT
# ─────────────────────────────────────────────────────────────
def setup_mqtt() -> mqtt.Client:
    # Client ID unique basé sur le UID de la borne — évite les conflits si relancé
    uid_short = (state.get("station_uid") or "unknown")[:8]
    mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"flo_x6_{uid_short}")

    if MQTT_USER:
        mqttc.username_pw_set(MQTT_USER, MQTT_PASS)

    # LWT — si le daemon crashe, HA marque tout comme indisponible
    # Le topic availability sera configuré après la découverte du UID
    # On utilisera un topic temporaire ici et on le reconfigurera après
    mqttc.on_connect    = on_connect
    mqttc.on_disconnect = on_disconnect
    mqttc.on_message    = on_message

    return mqttc

def connect_mqtt(mqttc: mqtt.Client, lwt_topic: str) -> bool:
    """Tente de se connecter au broker MQTT avec retry infini au démarrage."""
    mqttc.will_set(lwt_topic, "offline", retain=True, qos=1)
    attempt = 0
    while True:
        try:
            mqttc.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            mqttc.loop_start()
            time.sleep(1)
            return True
        except Exception as e:
            attempt += 1
            delay = min(30, attempt * 5)  # 5s, 10s, 15s... max 30s entre chaque retry
            log.warning("Broker MQTT inaccessible (tentative %d) : %s — retry dans %ds.",
                        attempt, e, delay)
            time.sleep(delay)

# ─────────────────────────────────────────────────────────────
# Boucle principale
# ─────────────────────────────────────────────────────────────
def poll_interval() -> int:
    """Retourne l'intervalle de polling adaptatif selon l'état EVSE."""
    evse = state.get("evse_status", "Unknown")
    if evse == "Charging":
        return POLL_CHARGING
    if evse in ("PluggedIn", "Reserved"):
        return POLL_PLUGGED
    return POLL_AVAILABLE

def run():
    global T

    log.info("Démarrage flo-x6-mqtt...")

    if not FLO_USERNAME or not FLO_PASSWORD:
        log.critical("FLO_USERNAME et FLO_PASSWORD sont requis.")
        sys.exit(1)

    # ── Auth initiale ────────────────────────────────────────
    log.info("Authentification Flo...")
    try:
        access_token = get_valid_access_token(FLO_USERNAME, FLO_PASSWORD, API_TIMEOUT)
    except FloAuthError as e:
        log.critical("Échec authentification : %s", e)
        sys.exit(1)
    except FloNetworkError as e:
        log.critical("Réseau indisponible au démarrage : %s", e)
        sys.exit(1)

    # ── Découverte UID borne ────────────────────────────────
    log.info("Récupération infos borne...")
    try:
        client  = FloX6Client(access_token, timeout=API_TIMEOUT)
        station = client.get_station()
        uid     = station["chargingStationUid"]
        state["station_uid"]   = uid
        state["evse_status"]   = station.get("evse", {}).get("status", "Unknown")
        T = topics(uid)
        log.info("Borne trouvée : %s (%s)", station.get("model"), uid[:8] + "...")
    except Exception as e:
        log.critical("Impossible de récupérer la borne : %s", e)
        sys.exit(1)

    # ── Connexion MQTT ──────────────────────────────────────
    mqttc = setup_mqtt()
    log.info("Connexion au broker MQTT %s:%s...", MQTT_HOST, MQTT_PORT)
    connect_mqtt(mqttc, T["availability"])  # retry infini, ne crashe plus

    # Publier discovery et s'abonner aux commandes
    publish_discovery(mqttc, station)
    mqttc.subscribe(T["command_charge"], qos=1)

    # ── Gestion arrêt propre ────────────────────────────────
    def shutdown(sig, frame):
        log.info("Arrêt demandé...")
        set_availability(mqttc, False, "Arrêt du daemon")
        publish_diagnostic(mqttc)
        time.sleep(0.5)
        mqttc.loop_stop()
        mqttc.disconnect()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT,  shutdown)

    log.info("Daemon démarré. Polling adaptatif : %ds/%ds/%ds (charge/branché/libre)",
             POLL_CHARGING, POLL_PLUGGED, POLL_AVAILABLE)

    # ── Boucle principale ────────────────────────────────────
    while True:
        try:
            # 1. Vérifier internet
            internet_ok = check_internet()
            state["internet_ok"] = internet_ok
            if not internet_ok:
                state["consecutive_errors"] += 1
                cause = "Internet non disponible"
                log.warning(cause) if state["consecutive_errors"] < ERROR_THRESHOLD \
                    else log.error(cause)
                if state["consecutive_errors"] >= ERROR_THRESHOLD:
                    set_availability(mqttc, False, cause)
                publish_diagnostic(mqttc)
                time.sleep(POLL_RETRY)
                continue

            # 2. Vérifier cloud Flo
            flo_ok = check_flo_api(timeout=5)
            state["flo_cloud_ok"] = flo_ok
            if not flo_ok:
                state["consecutive_errors"] += 1
                cause = "Cloud Flo inaccessible"
                log.warning(cause) if state["consecutive_errors"] < ERROR_THRESHOLD \
                    else log.error(cause)
                if state["consecutive_errors"] >= ERROR_THRESHOLD:
                    set_availability(mqttc, False, cause)
                publish_diagnostic(mqttc)
                time.sleep(POLL_RETRY)
                continue

            # 3. Rafraîchir le token si nécessaire
            tokens = load_tokens()
            try:
                access_token = get_valid_access_token(FLO_USERNAME, FLO_PASSWORD, API_TIMEOUT)
                client.update_token(access_token)
            except FloAuthError as e:
                state["consecutive_errors"] += 1
                cause = f"Authentification expirée : {e}"
                log.error(cause)
                if state["consecutive_errors"] >= ERROR_THRESHOLD:
                    set_availability(mqttc, False, cause)
                publish_diagnostic(mqttc)
                time.sleep(POLL_RETRY)
                continue

            # 4. Appels API
            station = client.get_station()
            session = client.get_session()

            # Mise à jour état interne
            state["evse_status"]       = station.get("evse", {}).get("status", "Unknown")
            state["connection_status"] = station.get("connectionStatus", "Unknown")

            # 5. Succès → publier état
            if state["consecutive_errors"] >= ERROR_THRESHOLD or not state["bridge_online"]:
                set_availability(mqttc, True)

            # Reconnexion MQTT détectée → republier discovery + availability + état complet
            if state["mqtt_reconnected"]:
                log.info("Reconnexion MQTT détectée — republication complète.")
                state["mqtt_reconnected"] = False
                publish_discovery(mqttc, station)
                set_availability(mqttc, True)

            state["consecutive_errors"] = 0
            state["last_success_ts"]    = time.time()
            state["last_error_cause"]   = ""

            publish_state(mqttc, station, session)
            publish_diagnostic(mqttc)

            interval = poll_interval()
            log.debug("Poll OK — EVSE=%s, next dans %ds.", state["evse_status"], interval)
            # Sleep interruptible : vérifie chaque seconde si une reconnexion MQTT est survenue
            for _ in range(interval):
                if state["mqtt_reconnected"]:
                    log.debug("Sleep interrompu — reconnexion MQTT détectée.")
                    break
                time.sleep(1)

        except FloNetworkError as e:
            state["consecutive_errors"] += 1
            cause = f"Erreur réseau : {e}"
            log.warning(cause) if state["consecutive_errors"] < ERROR_THRESHOLD \
                else log.error(cause)
            state["last_error_cause"] = cause
            if state["consecutive_errors"] >= ERROR_THRESHOLD:
                set_availability(mqttc, False, cause)
            publish_diagnostic(mqttc)
            time.sleep(POLL_RETRY)

        except FloAPIError as e:
            state["consecutive_errors"] += 1
            cause = f"Erreur API : {e}"
            log.warning(cause) if state["consecutive_errors"] < ERROR_THRESHOLD \
                else log.error(cause)
            state["last_error_cause"] = cause
            if state["consecutive_errors"] >= ERROR_THRESHOLD:
                set_availability(mqttc, False, cause)
            publish_diagnostic(mqttc)
            time.sleep(POLL_RETRY)

        except Exception as e:
            # Filet de sécurité — le daemon ne meurt jamais sur une exception inattendue
            state["consecutive_errors"] += 1
            cause = f"Erreur inattendue : {type(e).__name__} : {e}"
            log.exception(cause)
            state["last_error_cause"] = cause
            if state["consecutive_errors"] >= ERROR_THRESHOLD:
                set_availability(mqttc, False, cause)
            publish_diagnostic(mqttc)
            time.sleep(POLL_RETRY)

if __name__ == "__main__":
    run()
