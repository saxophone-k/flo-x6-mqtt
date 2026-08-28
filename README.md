# flo-x6-mqtt

**Local control of a FLO Home X6 EV charger through Home Assistant — no FLO cloud.**

The charger speaks **OCPP 1.6** to a tiny local server (this bridge) instead of FLO's cloud.
The bridge translates OCPP into MQTT with Home Assistant discovery, and HA commands back into
OCPP. Once set up you can WAN-block the charger entirely: it keeps charging and stays fully
controllable from HA, with nothing leaving your LAN.

```
  EV charger ──OCPP 1.6 (ws)──▶ flo-x6-mqtt ──MQTT──▶ Mosquitto ──▶ Home Assistant
   (192.168.x.x)                (this bridge)                        (device + entities)
```

> ## ⚠ v2 is a complete redesign (breaking change from v1)
> **v1** was a *cloud* bridge — it impersonated the FLO app against `emobility.flo.ca`. It still
> works but depends on FLO's cloud. **v2 (this)** is **local**: the charger connects directly to
> the bridge over OCPP, zero cloud. They are not compatible — v2 requires a one-time **repoint**
> of the charger (below). The v1 cloud bridge is preserved under [`legacy-cloud/`](legacy-cloud/).
> See [`MIGRATION.md`](MIGRATION.md).

> ## Disclaimer
> This is an independent, reverse-engineered project. **Not affiliated with or endorsed by FLO /
> AddÉnergie.** Use on hardware you own. No warranty.

## Why this is possible (and the honest caveat)

This is **not** a crack of FLO's cloud security — that part is genuinely solid (mutual-TLS with a
per-device certificate we can't extract). Instead, it works thanks to a **small open door FLO
left in the charger's setup procedure.**

When the charger is in Wi-Fi pairing (AP) mode, it serves a **plain, unauthenticated local
config API** (`http://192.168.9.1/onboarding/…`) — the very same one the FLO app uses to set
your home Wi-Fi and register the charger. One of the values that API writes is the charger's
**OCPP server URL**, and FLO left that field wide open: no login, no signed config, no locked-in
address. So we simply **join the setup Wi-Fi and write our own server's address** where FLO's
cloud URL used to be. We're not breaking in — we walk through the same door FLO uses itself, and
the charger happily reports to us instead. The charger even accepts a plain `ws://` OCPP URL, so
there's nothing to defeat.

> ⚠ **Because this depends on that open door, a future FLO firmware update could close it** — by
> adding authentication to the setup API, signing the config, or hardcoding the server URL.
> If that happens, **chargers already repointed keep working**, but new repoints might not, and
> a forced firmware update could in principle undo an existing one. Blocking the charger's
> internet access (the WAN-block step) is what protects an existing setup from that.

---

## What you get

One HA **device** ("Flo Home X6") with 14 entities:

| Entity | Type | Notes |
|---|---|---|
| Status | sensor | OCPP connector status (Available / Preparing / Charging / SuspendedEV / …) |
| Power | sensor (W) | live power (charger's own reading, or V×I) |
| Current | sensor (A) | current the car is drawing |
| Current Offered | sensor (A) | **display-only** — set by the charger's internal rotary switch (your breaker/wiring max), not software-settable |
| Voltage | sensor (V) | |
| Session Energy | sensor (Wh) | this session |
| Total Energy | sensor (Wh) | lifetime meter → **HA Energy dashboard** (`total_increasing`) |
| Plugged In / Charging | binary_sensor | |
| **OCPP Connected** | binary_sensor | is the charger's link to the bridge alive (heartbeat-driven) |
| **Last Seen** | sensor (timestamp) | last message from the charger |
| Charge Lock | switch | block charging at the station (OCPP auth-rejection) |
| Start / Stop Charging | button | RemoteStart / RemoteStop |

**No stale data:** every telemetry/control entity requires **both** the bridge *and* the charger
to be online; if either drops, the entities go **unavailable** in HA (never a frozen value). The
OCPP-Connected / Last-Seen pair stay available so they can report the offline state.

---

## Requirements

- A **FLO Home X6** on your LAN (see compatibility below).
- An **MQTT broker** (e.g. Mosquitto) + Home Assistant with the MQTT integration.
- A host to run this (Docker / TrueNAS SCALE / etc.) that the **charger can reach on the OCPP
  port** — i.e. same LAN/VLAN as the charger, or a firewall permit to it.
- The charger's **setup Wi-Fi credentials** for the one-time repoint (see the recipe). These are
  on the **pairing card / QR that came in the box**; if you tossed it, **FLO support can provide
  them** for your serial.

### Compatibility

| Model | Status |
|---|---|
| **FLO Home X6** | ✅ verified (firmware 3.1.7) |
| FLO Home X5 / X8 | 🟡 untested — likely the same `/onboarding` API; **reports welcome** |

---

## Quick start

1. **Deploy the bridge** (pick an install option below) and point it at your MQTT broker. It
   listens for the charger on **`ws://<host>:9000`**. The HA device appears immediately (entities
   *unavailable* until the charger connects).
2. **Repoint the charger** to `ws://<host>:9000/flo` — see [`REPOINT.md`](REPOINT.md). One-time,
   ~10 minutes, no soldering.
3. The charger connects; entities come alive in HA. Optionally **WAN-block** the charger.

---

## Repointing the charger (the one-time setup)

Use the guided helper — **`repoint_ui.py`** opens a page in your browser; you just type your
server's IP and click a button. Do these **in order** (steps 1–2 need internet; from step 3 on
you'll be on the charger's own Wi-Fi, which has **no internet** — that's normal). Full detail +
a `curl` alternative in [`REPOINT.md`](REPOINT.md).

1. **Install Python 3** — macOS/Linux already have it; on Windows install from
   [python.org](https://www.python.org/downloads/) and **tick "Add Python to PATH."**
2. **Download `repoint_ui.py`** from this repo — do it now, while you still have internet.
3. **Put the charger in pairing mode:** press and **hold the connector ("gun") button for 10+
   seconds**, until the charger's own Wi-Fi **`AP_FLO_xxxx`** appears in your laptop's Wi-Fi list.
   *(This pairing window is the only time the setup works.)*
4. **Join `AP_FLO_xxxx`** from your laptop (password is on the box's pairing card). Your laptop
   loses internet now — expected, you already downloaded everything.
5. **Run it** — Windows: **double-click** `repoint_ui.py`; macOS/Linux: `python3 repoint_ui.py`.
   Your browser opens to the setup page.
6. **Type your server's IP**, click **Point charger at my server**, then **Finish**.
7. The charger **automatically leaves pairing mode and stays on your home Wi-Fi** — now reporting
   to *your* bridge (you don't reconfigure its Wi-Fi). Just **reconnect your laptop's Wi-Fi** to
   your home network, and check Home Assistant.

---

## Install

Every method uses the same image + the same env vars; only your broker details change.

### Docker
```bash
docker run -d --name flo-x6-mqtt --restart unless-stopped \
  -p 9000:9000 --env-file .env \
  ghcr.io/saxophone-k/flo-x6-mqtt:latest
```

### docker-compose
Edit `.env`, then `docker compose up -d` (see [`docker-compose.yml`](docker-compose.yml)).

### TrueNAS SCALE (custom app)
- Image `ghcr.io/saxophone-k/flo-x6-mqtt:latest`
- **Host networking** (so the charger can reach the bridge on the host's IP:9000)
- Restart policy **Unless Stopped**
- Env vars (below). No storage needed — the bridge is stateless.
- **If your charger is on an isolated IoT VLAN:** give the host an interface on that VLAN and
  run the app host-networked there, so the charger reaches the bridge **same-VLAN** (no ACL).
  Otherwise add a firewall permit `charger → host:9000`.

### Home Assistant OS add-on
Wrap the image in a local add-on (a `config.yaml` + `Dockerfile: FROM ghcr.io/...`); set the
env vars as add-on options.

---

## Configuration (environment variables)

| Variable | Default | |
|---|---|---|
| `FLO_MQTT_HOST` | `192.168.10.100` | your broker |
| `FLO_MQTT_PORT` | `1883` | |
| `FLO_MQTT_USER` / `FLO_MQTT_PASS` | *(empty)* | broker auth, if any |
| `FLO_OCPP_PORT` | `9000` | port the charger connects to |
| `FLO_DEVICE_NAME` / `FLO_DEVICE_ID` | `Flo Home X6` / `flo_x6` | HA device name / slug |
| `FLO_MQTT_PREFIX` | `flo-x6` | base MQTT topic |
| `FLO_HA_DISCOVERY_PREFIX` | `homeassistant` | |
| `FLO_HEARTBEAT_INTERVAL` | `30` | seconds |
| `FLO_LOG_LEVEL` | `INFO` | |

> The **charger→bridge URL is not configured in the bridge** — it's set on the charger during
> the repoint. The bridge just listens on `0.0.0.0:FLO_OCPP_PORT`.

---

## WAN-blocking the charger (the whole point)

Once repointed, block the charger from the internet to kill the FLO cloud/EMS channels and any
OTA. **Charging and all HA control keep working** — they're local now.

- Rule: **deny `<charger-ip> → WAN`**. No allow rule needed for the bridge if they're same-VLAN.
- What dies: FLO app, remote (off-LAN) access, firmware updates, cloud telemetry.
- What stays: charging, HA control, local telemetry.

> ### ⚠ Known behaviour: slow reconnect while WAN-blocked
> The X6 pings `8.8.8.8` as a connectivity check. WAN-blocked, it decides it's "offline" (red
> connectivity light) and **backs off its reconnect** — so after a bridge restart or charger
> reboot it can take **up to ~an hour** to reconnect (charging is unaffected the whole time).
> It **does** reconnect on its own. Options:
> - Accept it (nudge with a breaker cycle to force an immediate fresh-boot reconnect); or
> - Allow just the probe out: **permit `<charger-ip> → 8.8.8.8` (ICMP only)** — the light stays
>   green and it reconnects fast, while the real FLO cloud stays blocked; or
> - Lower the charger's `WebSocketPingInterval` via OCPP (this bridge can, see below) so it
>   detects a dead link faster.

---

## How it works

- The charger is an **OCPP 1.6 charge point**; this bridge is the **Central System** it dials
  into (plain `ws://` — the X6 does not require TLS for OCPP).
- It **auto-starts** transactions (no RFID needed), so **Stop** is the everyday control.
- Repoint uses the charger's **SoftAP setup API** (`http://192.168.9.1/onboarding/*`), served
  only while the charger is in pairing/AP mode. The OCPP config body is **snake_case**
  (`ocpp_url` / `ocpp_username` / `ocpp_password`) — camelCase returns HTTP 422.
- **OCPP config get/set:** publish `get_config` / `set_config` (e.g. `WebSocketPingInterval=30`)
  to `flo-x6/<id>/cmd/...` to read/tune the charger's OCPP settings.

---

## Troubleshooting

- **HTTP 422 on repoint** → body must be snake_case (`ocpp_url`, not `ocppUrl`).
- **Charger won't connect** → confirm the bridge is reachable from the charger's network on the
  OCPP port; check the charger's connectivity light (red = it thinks it's offline — see WAN-block
  note). Check the container logs for `Charger connected: …`.
- **Entities unavailable** → that's by design when the charger or bridge is offline. Check the
  `OCPP Connected` sensor and the container logs.
- **Slow reconnect after a restart** → see the WAN-block note above.

## Contributing
Reports from **X5 / X8** owners especially welcome (does the `/onboarding` repoint work?).

## License
MIT. Not affiliated with FLO / AddÉnergie.
