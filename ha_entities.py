"""Home Assistant MQTT-discovery entity definitions for the Flo X6 bridge.

One HA *device* holds every entity. Each entry becomes a discovery config published to
`<disc>/<component>/<node>/<object_id>/config`, with state on topics under `<prefix>/...`.
"""


def device_block(cfg):
    return {
        "identifiers": [cfg.DEVICE_ID],
        "name": cfg.DEVICE_NAME,
        "manufacturer": "FLO",
        "model": "Home X6",
    }


def base_topic(cfg):
    return f"{cfg.MQTT_PREFIX}/{cfg.DEVICE_ID}"


def availability(cfg):
    # LWT-backed availability so entities grey out if the bridge dies.
    return {"availability_topic": f"{base_topic(cfg)}/availability",
            "payload_available": "online", "payload_not_available": "offline"}


def entities(cfg):
    """Return list of (component, object_id, discovery_config)."""
    t = base_topic(cfg)
    dev = device_block(cfg)
    av = availability(cfg)

    def sensor(oid, name, state_key, unit=None, dclass=None, sclass=None, icon=None):
        c = {"name": name, "unique_id": f"{cfg.DEVICE_ID}_{oid}",
             "state_topic": f"{t}/state", "value_template": "{{ value_json.%s }}" % state_key,
             "device": dev, **av}
        if unit: c["unit_of_measurement"] = unit
        if dclass: c["device_class"] = dclass
        if sclass: c["state_class"] = sclass
        if icon: c["icon"] = icon
        return ("sensor", oid, c)

    def binary(oid, name, state_key, dclass=None, icon=None):
        c = {"name": name, "unique_id": f"{cfg.DEVICE_ID}_{oid}",
             "state_topic": f"{t}/state", "value_template": "{{ value_json.%s }}" % state_key,
             "payload_on": "true", "payload_off": "false", "device": dev, **av}
        if dclass: c["device_class"] = dclass
        if icon: c["icon"] = icon
        return ("binary_sensor", oid, c)

    items = [
        # --- read-only telemetry ---
        sensor("status", "Status", "status", icon="mdi:ev-station"),
        sensor("power", "Power", "power_w", "W", "power", "measurement"),
        sensor("current_import", "Current", "current_a", "A", "current", "measurement"),
        sensor("current_offered", "Current Offered", "current_offered_a", "A", "current",
               "measurement", icon="mdi:speedometer"),  # display-only (hardware rotary dial)
        sensor("voltage", "Voltage", "voltage_v", "V", "voltage", "measurement"),
        sensor("session_energy", "Session Energy", "session_energy_wh", "Wh", "energy",
               "total_increasing"),
        sensor("total_energy", "Total Energy", "total_energy_wh", "Wh", "energy",
               "total_increasing"),  # lifetime meter -> HA Energy dashboard
        binary("plugged", "Plugged In", "plugged", "plug"),
        binary("charging", "Charging", "charging", "battery_charging"),
        # --- controls ---
        # Charge Lock: on = block charging (OCPP auth-rejection). Verify honored on hardware.
        ("switch", "charge_lock", {
            "name": "Charge Lock", "unique_id": f"{cfg.DEVICE_ID}_charge_lock",
            "state_topic": f"{t}/state", "value_template": "{{ value_json.charge_lock }}",
            "command_topic": f"{t}/cmd/charge_lock",
            "payload_on": "true", "payload_off": "false", "icon": "mdi:lock", "device": dev, **av}),
    ]
    # Start / Stop as buttons (charger auto-starts, so Stop is the everyday lever).
    for oid, name, payload, icon in [
        ("start", "Start Charging", "start", "mdi:play"),
        ("stop", "Stop Charging", "stop", "mdi:stop"),
    ]:
        items.append(("button", oid, {
            "name": name, "unique_id": f"{cfg.DEVICE_ID}_{oid}",
            "command_topic": f"{t}/cmd/{oid}", "payload_press": payload,
            "icon": icon, "device": dev, **av}))
    return items
