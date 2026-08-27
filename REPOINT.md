# Repointing the charger to your local server

One-time, ~10 minutes, no soldering. You change the charger's **OCPP server URL** from FLO's
cloud to your bridge, using the charger's own setup API (the same one the FLO app uses).

> Do this on hardware you own. It's reversible (re-pair with the FLO app restores the cloud
> config). Have the bridge already running first, so the charger has something to connect to.

## 0. What you need

- The bridge deployed and listening on `ws://<host>:9000` (your host's LAN IP).
- The charger's **setup Wi-Fi credentials** (the `AP_FLO_xxxx` network's name + WPA2 password).
  These are printed on the **pairing card / QR** from the box. **Lost it?** FLO support can give
  you the setup Wi-Fi SSID + password for your serial — just ask.
- A laptop/phone that can join the charger's setup Wi-Fi and run `curl` (or any HTTP tool).

## 1. Put the charger in setup (AP) mode

Press and **hold the connector button ~10 seconds** until the connectivity light changes.
Depending on firmware the light goes **orange, then blinks** — wait until it settles/steady and
the setup Wi-Fi `AP_FLO_xxxx` is broadcasting. (If it goes red, it's not in AP mode — re-do the
hold.)

## 2. Join the charger's setup Wi-Fi

From your laptop, connect Wi-Fi to **`AP_FLO_xxxx`** using the password from the card / FLO. You
get an IP like `192.168.9.x`; the charger is at **`192.168.9.1`**.

> Tip: keep a *wired* connection to your normal LAN at the same time (so you don't lose internet
> / access to the bridge). The two interfaces coexist.

## 3. Read the current config (safe, no changes)

```bash
curl http://192.168.9.1/onboarding/ocpp_status
curl http://192.168.9.1/onboarding/wifi_status
```
`ocpp_status` shows the current cloud URL + username; `wifi_status` shows the home Wi-Fi it's on.
(The charger ignores ICMP — `ping` won't work, but HTTP does.)

## 4. Point it at your bridge

**⚠ The body is snake_case.** camelCase returns HTTP 422.

```bash
curl -X PUT http://192.168.9.1/onboarding/ocpp_configuration \
  -H 'Content-Type: application/json' \
  -d '{"ocpp_url":"ws://<HOST-IP>:9000/flo","ocpp_username":"flo","ocpp_password":"flo"}'
```
- `<HOST-IP>` = the LAN IP of the machine running the bridge (e.g. `192.168.107.100`).
- `ocpp_username` / `ocpp_password` can be anything — the bridge accepts any charge point.
- The path segment (`/flo`) becomes the charge-point id in the bridge logs; pick anything.

Optional — if you want the charger to also switch home Wi-Fi (usually leave it as-is):
```bash
curl -X PUT http://192.168.9.1/onboarding/wifi_configuration \
  -H 'Content-Type: application/json' \
  -d '{"wifi_ssid":"YourSSID","wifi_password":"YourPass"}'
```

Verify it took (should now show your URL and `status` moving to `CONNECTED`):
```bash
curl http://192.168.9.1/onboarding/ocpp_status
```

## 5. Finalize

```bash
curl -X POST http://192.168.9.1/onboarding/exit
```
The charger leaves AP mode and rejoins your normal Wi-Fi, now talking to your bridge.

## 6. Confirm

In Home Assistant the "Flo Home X6" device entities should come alive (Status `Available`, then
telemetry when you plug in). Bridge container logs show `Charger connected: /flo`.

## Revert to FLO cloud

Re-pair the charger with the **FLO app** (using the same setup Wi-Fi creds) — it re-provisions
the original cloud OCPP config from FLO. (We overwrite `ocpp_url/username/password`, so there's
no one-command undo; re-pairing is the clean restore.)

## Notes / gotchas

- `/onboarding/*` is served **only in AP mode** — on the charger's normal LAN IP it returns 502.
- The charger accepts plain **`ws://`** (no TLS needed).
- After WAN-blocking, expect a **slow reconnect** on the next restart — see the README.
