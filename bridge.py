"""flo-x6-mqtt v2 — local OCPP 1.6 → MQTT/Home-Assistant bridge for the FLO Home X6.

The charger connects TO this server (we are the OCPP Central System). We translate its
OCPP messages into MQTT state for Home Assistant, and translate HA commands (start / stop /
charge-lock) back into OCPP calls to the charger. No FLO cloud involved.
"""
import asyncio
import json
import logging
import datetime
import time

import websockets
from ocpp.v16 import ChargePoint as CP, call, call_result
from ocpp.v16.enums import Action, RegistrationStatus, AuthorizationStatus, RemoteStartStopStatus
from ocpp.routing import on

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None

from config import Config
import ha_entities

log = logging.getLogger("flo-bridge")


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


PLUGGED_STATES = {"Preparing", "Charging", "SuspendedEV", "SuspendedEVSE", "Finishing"}
# If the charger goes silent longer than this (3 missed 30s heartbeats), call it offline.
STALE_AFTER = 95


class State:
    """Shared, JSON-serialisable charger state published to HA."""
    def __init__(self):
        self.status = "Unknown"
        self.power_w = 0.0
        self.current_a = 0.0
        self.current_offered_a = 0.0
        self.voltage_v = 0.0
        self.total_energy_wh = 0.0
        self.session_energy_wh = 0.0
        self._meter_start = None
        self.charge_lock = False
        self.transaction_id = None
        self.connected = False          # charger's OCPP link (heartbeat-driven)
        self.last_seen = None           # ISO time of last OCPP message
        self._last_seen_mono = 0.0      # monotonic, for the staleness watchdog

    def as_json(self):
        return json.dumps({
            "status": self.status,
            "power_w": round(self.power_w, 1),
            "current_a": round(self.current_a, 2),
            "current_offered_a": round(self.current_offered_a, 1),
            "voltage_v": round(self.voltage_v, 1),
            "total_energy_wh": round(self.total_energy_wh, 1),
            "session_energy_wh": round(self.session_energy_wh, 1),
            "plugged": str(self.status in PLUGGED_STATES).lower(),
            "charging": str(self.status == "Charging").lower(),
            "charge_lock": str(self.charge_lock).lower(),
            "connected": str(self.connected).lower(),
            "last_seen": self.last_seen,
        })


class MqttPublisher:
    """Thin paho wrapper. In DRY_RUN it just logs, so we can test with no broker."""
    def __init__(self, cfg, on_command):
        self.cfg = cfg
        self.on_command = on_command  # callable(cmd_name, payload)
        self.client = None
        self._base = ha_entities.base_topic(cfg)

    def connect(self):
        if self.cfg.DRY_RUN or mqtt is None:
            log.info("MQTT DRY_RUN — publishes will be logged, not sent")
            self._publish_discovery()
            self.publish_availability("online")
            return
        try:  # paho-mqtt 2.x requires an explicit callback API version; keep v1 signatures
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        except (AttributeError, TypeError):
            self.client = mqtt.Client()
        if self.cfg.MQTT_USER:
            self.client.username_pw_set(self.cfg.MQTT_USER, self.cfg.MQTT_PASS)
        self.client.will_set(f"{self._base}/availability", "offline", retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.connect(self.cfg.MQTT_HOST, self.cfg.MQTT_PORT, 60)
        self.client.loop_start()

    def _on_connect(self, client, userdata, flags, rc):
        log.info(f"MQTT connected rc={rc}")
        self._publish_discovery()
        client.subscribe(f"{self._base}/cmd/#")
        self.publish_availability("online")

    def _on_message(self, client, userdata, msg):
        cmd = msg.topic.rsplit("/", 1)[-1]
        payload = msg.payload.decode(errors="replace")
        log.info(f"MQTT cmd: {cmd} = {payload}")
        self.on_command(cmd, payload)

    def _publish_discovery(self):
        for component, oid, cfgobj in ha_entities.entities(self.cfg):
            topic = f"{self.cfg.HA_DISCOVERY_PREFIX}/{component}/{self.cfg.DEVICE_ID}/{oid}/config"
            self._raw(topic, json.dumps(cfgobj), retain=True)

    def _raw(self, topic, payload, retain=False):
        if self.cfg.DRY_RUN or self.client is None:
            log.info(f"[MQTT] {topic} = {payload[:120]}")
        else:
            self.client.publish(topic, payload, retain=retain)

    def publish_state(self, state):
        self._raw(f"{self._base}/state", state.as_json(), retain=True)

    def publish_availability(self, val):
        self._raw(f"{self._base}/availability", val, retain=True)


class FloChargePoint(CP):
    """Handles the OCPP conversation for one connected charger."""
    def __init__(self, cp_id, connection, bridge):
        super().__init__(cp_id, connection)
        self.bridge = bridge

    def _pub(self):
        self.bridge.touch_seen()
        self.bridge.mqtt.publish_state(self.bridge.state)

    @on(Action.boot_notification)
    async def on_boot(self, charge_point_vendor, charge_point_model, **kw):
        log.info(f"Boot: {charge_point_vendor} {charge_point_model} {kw}")
        self._pub()
        return call_result.BootNotification(
            current_time=_now(), interval=self.bridge.cfg.HEARTBEAT_INTERVAL,
            status=RegistrationStatus.accepted)

    @on(Action.heartbeat)
    async def on_heartbeat(self):
        # Republish state on every heartbeat so HA gets a fresh reading even when idle,
        # and last_seen/connected stay current.
        self._pub()
        return call_result.Heartbeat(current_time=_now())

    @on(Action.status_notification)
    async def on_status(self, connector_id, error_code, status, **kw):
        # connector 0 = whole station; 1 = the plug. Track the plug.
        if connector_id in (0, 1):
            self.bridge.state.status = status
            if status not in PLUGGED_STATES:
                self.bridge.state.power_w = 0.0
                self.bridge.state.current_a = 0.0
            log.info(f"Status: connector={connector_id} {status} ({error_code})")
            self._pub()
        return call_result.StatusNotification()

    @on(Action.authorize)
    async def on_authorize(self, id_tag, **kw):
        status = AuthorizationStatus.blocked if self.bridge.state.charge_lock \
            else AuthorizationStatus.accepted
        return call_result.Authorize(id_tag_info={"status": status})

    @on(Action.start_transaction)
    async def on_start(self, connector_id, id_tag, meter_start, timestamp, **kw):
        s = self.bridge.state
        # Charge Lock: refuse the transaction so the charger won't deliver energy.
        if s.charge_lock:
            log.info("StartTransaction refused — Charge Lock ON")
            return call_result.StartTransaction(
                transaction_id=0, id_tag_info={"status": AuthorizationStatus.blocked})
        s.transaction_id = 1
        s._meter_start = float(meter_start)
        s.total_energy_wh = float(meter_start)
        s.session_energy_wh = 0.0
        log.info(f"StartTransaction meterStart={meter_start}")
        self._pub()
        return call_result.StartTransaction(
            transaction_id=s.transaction_id, id_tag_info={"status": AuthorizationStatus.accepted})

    @on(Action.stop_transaction)
    async def on_stop(self, meter_stop, timestamp, transaction_id, **kw):
        s = self.bridge.state
        s.total_energy_wh = float(meter_stop)
        if s._meter_start is not None:
            s.session_energy_wh = float(meter_stop) - s._meter_start
        s.transaction_id = None
        s.power_w = 0.0
        s.current_a = 0.0
        log.info(f"StopTransaction meterStop={meter_stop} reason={kw.get('reason')}")
        self._pub()
        return call_result.StopTransaction()

    @on(Action.meter_values)
    async def on_meter(self, connector_id, meter_value, **kw):
        s = self.bridge.state
        power_measurand = None
        for mv in meter_value:
            for sv in mv.get("sampled_value", []):
                meas = sv.get("measurand", "Energy.Active.Import.Register")
                try:
                    val = float(sv["value"])
                except (ValueError, KeyError):
                    continue
                if meas == "Energy.Active.Import.Register":
                    s.total_energy_wh = val
                    if s._meter_start is not None:
                        s.session_energy_wh = val - s._meter_start
                elif meas == "Current.Import":
                    s.current_a = val
                elif meas == "Current.Offered":
                    s.current_offered_a = val
                elif meas == "Voltage":
                    s.voltage_v = val
                elif meas == "Power.Active.Import":
                    power_measurand = val
        # Prefer the charger's own power reading; else derive V*I.
        s.power_w = power_measurand if power_measurand is not None else s.voltage_v * s.current_a
        self._pub()
        return call_result.MeterValues()

    # --- commands from HA (called on the asyncio loop) ---
    async def remote_start(self):
        r = await self.call(call.RemoteStartTransaction(id_tag="HA0000000000"))
        log.info(f"RemoteStart -> {r.status}")

    async def remote_stop(self):
        tid = self.bridge.state.transaction_id or 1
        r = await self.call(call.RemoteStopTransaction(transaction_id=tid))
        log.info(f"RemoteStop(tx={tid}) -> {r.status}")


class Bridge:
    def __init__(self, cfg):
        self.cfg = cfg
        self.state = State()
        self.cp = None            # latest connected charger
        self.loop = None
        self.mqtt = MqttPublisher(cfg, self._handle_command)

    def _handle_command(self, cmd, payload):
        """Runs on paho's thread — marshal onto the asyncio loop."""
        s = self.state
        if cmd == "charge_lock":
            s.charge_lock = (payload.strip().lower() in ("true", "on", "1"))
            log.info(f"Charge Lock -> {s.charge_lock}")
            # If locking mid-session, stop the active transaction too.
            if s.charge_lock and self.cp and s.transaction_id:
                self._schedule(self.cp.remote_stop())
            self.mqtt.publish_state(s)
        elif cmd == "start" and self.cp:
            self._schedule(self.cp.remote_start())
        elif cmd == "stop" and self.cp:
            self._schedule(self.cp.remote_stop())

    def _schedule(self, coro):
        if self.loop:
            asyncio.run_coroutine_threadsafe(coro, self.loop)

    def touch_seen(self):
        """Mark the charger as alive (called on every inbound OCPP message)."""
        self.state.connected = True
        self.state.last_seen = _now()
        self.state._last_seen_mono = time.monotonic()

    async def _watchdog(self):
        """If the charger goes silent past STALE_AFTER, flag it offline in HA."""
        while True:
            await asyncio.sleep(20)
            s = self.state
            if s.connected and (time.monotonic() - s._last_seen_mono) > STALE_AFTER:
                log.warning("Charger silent > %ss — marking Offline", STALE_AFTER)
                s.connected = False
                s.status = "Offline"
                self.mqtt.publish_state(s)

    async def _on_connect(self, websocket):
        path = websocket.request.path
        cp_id = path.strip("/") or "flo"
        log.info(f"Charger connected: {cp_id}")
        self.cp = FloChargePoint(cp_id, websocket, self)
        self.touch_seen()
        self.mqtt.publish_state(self.state)
        try:
            await self.cp.start()
        except websockets.exceptions.ConnectionClosed:
            log.info("Charger disconnected")
            self.state.connected = False
            self.state.status = "Offline"
            self.mqtt.publish_state(self.state)

    async def run(self):
        logging.basicConfig(level=getattr(logging, self.cfg.LOG_LEVEL, logging.INFO),
                            format="%(asctime)s %(levelname)s %(name)s: %(message)s")
        self.loop = asyncio.get_running_loop()
        self.mqtt.connect()
        asyncio.ensure_future(self._watchdog())
        log.info(f"OCPP CSMS listening ws://{self.cfg.OCPP_HOST}:{self.cfg.OCPP_PORT}")
        async with websockets.serve(self._on_connect, self.cfg.OCPP_HOST, self.cfg.OCPP_PORT,
                                    subprotocols=["ocpp1.6"]):
            await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(Bridge(Config).run())
