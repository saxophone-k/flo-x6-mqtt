# flo-x6-mqtt

Bridge between the **Flo X6 home EV charger** and **Home Assistant** via MQTT.

Polls the Flo cloud API and publishes real-time charging data using Home Assistant MQTT Discovery — no manual entity configuration required.

---

> ⚠️ **Disclaimer — Please read before using**
>
> This project is **not affiliated with, endorsed by, or supported by Flo / AddEnergie** in any way.
>
> The Flo X6 API used here is **undocumented and unofficial**. It was reverse-engineered from the Android APK and network traffic capture. This means:
> - It can **break without warning** if Flo updates their app, API, or authentication system
> - Your account credentials are used to poll the API — use at your own risk
> - There is no guarantee this will keep working
>
> **I am not a developer.** This project was built with the help of AI. If something breaks, I may or may not be able to fix it. Feel free to open an issue and troubleshoot it with AI yourself — that's how this was built.
>
> **Use at your own risk.**

---

## Features

- **Auto-discovery**: 24 entities appear automatically in Home Assistant on first run
- **Real-time data**: current (A), voltage (V), power (W), energy (kWh), cost ($)
- **Smart polling**: 30s while charging, 60s plugged in, 120s when idle
- **Availability management**: entities go `unavailable` in HA when internet or Flo cloud is unreachable
- **Auto-reconnect**: recovers automatically from MQTT broker or internet outages
- **Start/Stop charging**: control your charger directly from Home Assistant
- **Bridge diagnostics**: monitor internet, Flo cloud, and bridge health from HA

## Entities

| Entity | Type | Description |
|--------|------|-------------|
| Charging | binary_sensor | Active charging session |
| Cable Plugged | binary_sensor | Cable connected |
| Connected | binary_sensor | Charger connected to Flo cloud |
| Error | binary_sensor | EVSE hardware fault |
| Session Active | binary_sensor | Session running |
| Schedule Active | binary_sensor | Schedule enabled |
| Current | sensor | Charging current (A) |
| Current Offered | sensor | Max available current (A) |
| Voltage | sensor | Charging voltage (V) |
| Power | sensor | Charging power (W) |
| Session Energy | sensor | Energy transferred this session (kWh) |
| Session Duration | sensor | Session duration (min) |
| Session Cost | sensor | Estimated cost ($) |
| Session State | sensor | Charging / Idle |
| EVSE Status | sensor | Available / PluggedIn / Charging / Inoperative |
| Charge | switch | Start / Stop charging |
| Internet | binary_sensor | Bridge internet connectivity (diagnostic) |
| Flo Cloud | binary_sensor | Flo API reachability (diagnostic) |
| Last Update | sensor | Timestamp of last successful poll (diagnostic) |
| Last Error | sensor | Last error cause (diagnostic) |
| Consecutive Errors | sensor | Error counter (diagnostic) |
| Firmware | sensor | Charger firmware version (diagnostic) |
| Max Amperage | sensor | Charger max amperage (diagnostic) |
| Schedule Mode | sensor | Manual / Scheduled (diagnostic) |

---

## Installation

### Option 1 — TrueNAS SCALE (Custom App)

1. In TrueNAS SCALE, go to **Apps** → **Discover Apps** → **Custom App**
2. Fill in the following:

**Application Name:** `flo-x6-mqtt`

**Image:**
- Repository: `ghcr.io/saxophone-k/flo-x6-mqtt`
- Tag: `latest`
- Pull Policy: `Always pull image before creating the container` *(pulls latest on each restart)*

**Environment Variables** — add each one:

| Name | Value |
|------|-------|
| `FLO_USERNAME` | Your Flo account email |
| `FLO_PASSWORD` | Your Flo account password |
| `HASS_MQTT_HOST` | Your MQTT broker IP (e.g. `192.168.1.100`) |
| `HASS_MQTT_PORT` | `1883` |
| `HASS_MQTT_USERNAME` | MQTT username *(if required)* |
| `HASS_MQTT_PASSWORD` | MQTT password *(if required)* |
| `LOG_LEVEL` | `INFO` |

**Storage** — add a persistent volume:
- Type: `ixVolume`
- Mount Path: `/app/data`
- Dataset name: `flo-x6-mqtt-data`

3. Click **Save** and wait for the app to show **Running**
4. In Home Assistant, go to **Settings → Devices & Services → MQTT** — the Flo Home X6 device should appear automatically

---

### Option 2 — Home Assistant OS (Add-on via Docker)

Home Assistant OS does not support arbitrary Docker containers natively, but you can run this bridge using one of these approaches:

**A) On a separate machine (Raspberry Pi, NAS, VM)**

Run Docker on any Linux machine on the same network as your MQTT broker:

```bash
docker run -d \
  --name flo-x6-mqtt \
  --restart unless-stopped \
  -e FLO_USERNAME=your@email.com \
  -e FLO_PASSWORD=yourpassword \
  -e HASS_MQTT_HOST=192.168.1.100 \
  -e HASS_MQTT_PORT=1883 \
  -v flo-x6-mqtt-data:/app/data \
  ghcr.io/saxophone-k/flo-x6-mqtt:latest
```

**B) Using docker-compose**

```yaml
services:
  flo-x6-mqtt:
    image: ghcr.io/saxophone-k/flo-x6-mqtt:latest
    container_name: flo-x6-mqtt
    restart: unless-stopped
    environment:
      - FLO_USERNAME=your@email.com
      - FLO_PASSWORD=yourpassword
      - HASS_MQTT_HOST=192.168.1.100
      - HASS_MQTT_PORT=1883
    volumes:
      - flo-x6-mqtt-data:/app/data

volumes:
  flo-x6-mqtt-data:
```

**C) Home Assistant OS with the SSH add-on**

Enable the **SSH & Web Terminal** add-on in HA OS, then use the docker commands from option A above.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FLO_USERNAME` | required | Flo account email |
| `FLO_PASSWORD` | required | Flo account password |
| `HASS_MQTT_HOST` | required | MQTT broker IP |
| `HASS_MQTT_PORT` | `1883` | MQTT broker port |
| `HASS_MQTT_USERNAME` | *(none)* | MQTT username |
| `HASS_MQTT_PASSWORD` | *(none)* | MQTT password |
| `POLL_INTERVAL_CHARGING` | `30` | Polling interval while charging (s) |
| `POLL_INTERVAL_PLUGGED` | `60` | Polling interval when plugged in (s) |
| `POLL_INTERVAL_AVAILABLE` | `120` | Polling interval when idle (s) |
| `POLL_INTERVAL_RETRY` | `60` | Retry interval on error (s) |
| `API_TIMEOUT` | `10` | Flo API request timeout (s) |
| `CONSECUTIVE_ERRORS_THRESHOLD` | `3` | Errors before marking unavailable |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

---

## Home Assistant Dashboard

A ready-to-use Lovelace dashboard is included in [`HOME_ASSISTANT_DASHBOARD.yaml`](HOME_ASSISTANT_DASHBOARD.yaml).

To add it:
1. Create a new dashboard in HA (**Settings → Dashboards → Add Dashboard**)
2. Open it → **Edit** → **three dots** → **Edit in YAML** (Raw configuration editor)
3. Paste the contents of `HOME_ASSISTANT_DASHBOARD.yaml`
4. Save

The dashboard includes:
- **Status** — charging/plugged state + conditional Start/Stop button (only appears when car is connected)
- **Live Session** — power gauge, current, voltage, energy, cost, duration
- **History** — power graph (2h) + daily energy bar chart (7 days)
- **Connectivity** — charger online, internet, Flo cloud, EVSE error, bridge diagnostics

---

## Home Assistant Automations

7 ready-to-use automations are included in [`HOME_ASSISTANT_AUTOMATIONS.yaml`](HOME_ASSISTANT_AUTOMATIONS.yaml):

| # | Automation | Trigger |
|---|-----------|---------|
| 1 | Vehicle Plugged In | Cable connected |
| 2 | Vehicle Unplugged | Cable disconnected *(includes session summary if was charging)* |
| 3 | Charging Started | Charge begins |
| 4 | Charging Stopped | Charge ends, car still connected |
| 5 | Bridge Offline | Internet lost for 3+ minutes |
| 6 | Flo Cloud Unreachable | API unreachable, internet up |
| 7 | EVSE Error | Hardware fault detected |

To add each automation:
1. **Settings → Automations & Scenes → + Create Automation**
2. Three dots → **Edit in YAML**
3. Paste one block at a time (separated by `---` in the file)
4. Update `notify.mobile_app_nicholass_iphone_14` to match **your** notification service

> To find your notification service: **Settings → Devices & Services → Mobile App** → your device name

---

## Home Assistant Energy Dashboard

The **Session Energy** sensor integrates natively with the HA Energy dashboard.

1. Go to **Settings → Energy** (or the Energy tab in the sidebar)
2. **Individual devices → Add device**
3. Select **Session Energy** (Flo Home X6)
4. Save

HA will accumulate daily/monthly kWh statistics automatically.

---

## Notes

- Authentication uses PingIdentity OAuth2 PKCE — tokens are cached in the `data/` volume and refreshed automatically (refresh token valid ~450 days)
- The Flo X6 reports to the cloud every ~30 seconds during active charging
- Compatible with **Flo X6 only** — not tested with X3, X5, or X8
- If Flo changes their API or authentication system, this bridge will stop working

## License

MIT
