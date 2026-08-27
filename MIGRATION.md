# Migrating from v1 (cloud) to v2 (local)

**v1** talked to FLO's cloud (`emobility.flo.ca`) by impersonating the app. **v2** makes the
charger talk **directly to a local OCPP server** (this bridge) — no cloud, WAN-blockable. This
is a one-time move; the two are not compatible.

The v1 cloud bridge is kept under [`legacy-cloud/`](legacy-cloud/) and on the `main` branch, so
it remains your rollback.

## Do it side-by-side (no downtime, easy rollback)

1. **Keep v1 running.** Don't delete the cloud app yet.
2. **Deploy v2 as a *new* app** (see the README). Point it at your MQTT broker. It listens on
   `ws://<host>:9000`. Give the v2 device a distinct name if you like (`FLO_DEVICE_NAME=Flo
   Home X6 Local`) so the two don't collide in HA while both run.
3. **Repoint the charger** to the v2 bridge — see [`REPOINT.md`](REPOINT.md). The charger stops
   talking to FLO's cloud and connects to your bridge.
4. **Verify v2** in HA (device online, telemetry when charging).
5. **Retire v1:** stop the cloud app. (Keep its config as rollback.)
6. **Optionally WAN-block** the charger — now safe (see the README's WAN-block section).

## What changes in Home Assistant

v2 is a **new MQTT device with new entities** (English IDs). Update your dashboards/automations:

| v1 (cloud) | v2 (local) |
|---|---|
| power / status / plugged / charging sensors | same concepts, new entity IDs (`sensor.flo_home_x6_power`, `binary_sensor.flo_home_x6_charging`, `..._plugged_in`) |
| Charge Lock (flips a FLO cloud *schedule*) | Charge Lock **switch** (OCPP auth-rejection — blocks at the station) |
| Start/Stop (cloud session API) | Start / Stop **buttons** (OCPP RemoteStart/Stop) |
| cloud-connectivity sensors | **OCPP Connected** + **Last Seen** (local link health) |
| — | **richer telemetry:** current, voltage, current-offered, session energy |

If you kept the same HA device name, the old (cloud) entities go **unavailable** once the cloud
app is stopped — delete that stale device under Settings → Devices → MQTT.

## Rollback to cloud

Re-pair the charger with the **FLO app** (it re-provisions the original cloud OCPP config), and
start the v1 cloud app again. See [`REPOINT.md`](REPOINT.md) → "Revert to FLO cloud."

## What you gain / lose going local

**Gain:** no cloud dependency, WAN-blockable, faster local control, live current/voltage/energy,
link-health sensors, no FLO account needed for control.
**Lose:** the FLO app's remote (off-LAN) access — use a VPN (Tailscale/WireGuard) into HA
instead — and FLO-side firmware updates (that's the point).
