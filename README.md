# flo-x6-mqtt

Bridge between the **Flo X6 home EV charger** and **Home Assistant** via MQTT.

Polls the Flo cloud API and publishes real-time charging data using Home Assistant MQTT Discovery — no manual entity configuration required.

## Features

- **Auto-discovery**: 24 entities appear automatically in Home Assistant on first run
- **Real-time data**: current (A), voltage (V), power (W), energy (kWh), cost ($)
- **Smart polling**: 30s while charging, 60s plugged in, 120s when idle
- **Availability management**: entities go `unavailable` in HA when internet or cloud is unreachable
- **Auto-reconnect**: recovers automatically from MQTT broker or internet outages
- **Start/Stop charging**: control your charger directly from Home Assistant
- **Bridge diagnostics**: monitor internet, Flo cloud, and bridge health from HA

## Entities

| Entity | Type | Description |
|--------|------|-------------|
| EVSE Status | sensor | Available / PluggedIn / Charging / Inoperative |
| Charging | binary_sensor | Active charging session |
| Cable Plugged | binary_sensor | Cable connected |
| Current | sensor | Charging current (A) |
| Voltage | sensor | Charging voltage (V) |
| Power | sensor | Charging power (W) |
| Session Energy | sensor | Energy transferred this session (kWh) |
| Session Duration | sensor | Session duration (min) |
| Session Cost | sensor | Estimated cost ($) |
| Session State | sensor | Charging / Idle |
| Charge | switch | Start / Stop charging |
| Internet | binary_sensor | Internet connectivity (diagnostic) |
| Flo Cloud | binary_sensor | Flo API reachability (diagnostic) |
| Last Update | sensor | Timestamp of last successful poll (diagnostic) |
| Last Error | sensor | Last error cause (diagnostic) |
| Consecutive Errors | sensor | Error counter (diagnostic) |

## Quick Start

### Docker (recommended)

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

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FLO_USERNAME` | required | Flo account email |
| `FLO_PASSWORD` | required | Flo account password |
| `HASS_MQTT_HOST` | required | MQTT broker IP |
| `HASS_MQTT_PORT` | `1883` | MQTT broker port |
| `HASS_MQTT_USERNAME` | _(none)_ | MQTT username |
| `HASS_MQTT_PASSWORD` | _(none)_ | MQTT password |
| `POLL_INTERVAL_CHARGING` | `30` | Polling interval while charging (s) |
| `POLL_INTERVAL_PLUGGED` | `60` | Polling interval when plugged in (s) |
| `POLL_INTERVAL_AVAILABLE` | `120` | Polling interval when idle (s) |
| `POLL_INTERVAL_RETRY` | `60` | Retry interval on error (s) |
| `API_TIMEOUT` | `10` | Flo API request timeout (s) |
| `CONSECUTIVE_ERRORS_THRESHOLD` | `3` | Errors before marking unavailable |
| `LOG_LEVEL` | `INFO` | Logging level |

## Home Assistant Energy Dashboard

The **Session Energy** sensor (`device_class: energy`, `state_class: total_increasing`) integrates natively with the Home Assistant Energy dashboard. Add it as an individual device consumption source to track charging history and costs.

## Notes

- Authentication uses PingIdentity OAuth2 PKCE — tokens are cached in the `data/` volume
- The Flo X6 reports to the cloud every ~30 seconds during active charging
- Compatible with Flo X6 only (not X3/X5)

## License

MIT
