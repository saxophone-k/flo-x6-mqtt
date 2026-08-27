# Repointing the charger to your local server

One-time, ~10 minutes, no soldering. You change the charger's **OCPP server URL** from FLO's
cloud to your own bridge, using the charger's built-in setup Wi-Fi (the same thing the FLO app
uses). It's reversible — re-pair with the FLO app to restore the cloud config.

**Before you start:**
- Have the **bridge already running** and note the **IP address** of the machine running it
  (e.g. `192.168.1.50`).
- Have the charger's **setup Wi-Fi password** — printed on the pairing card/QR from the box.
  **Lost it?** FLO support can give you the setup Wi-Fi name + password for your serial.

---

## The easy way — the guided helper (recommended)

Run **`repoint_tool.py`** and just follow the prompts — it walks you through putting the charger
in setup mode and joining its Wi-Fi, then does the rest with confirmations and clear error
messages. No commands to type.

```bash
python repoint_tool.py
```
*(No dependencies — any Python 3 works. A double-click packaged version may be attached to the
[Releases](../../releases) page.)*

That's it. When it finishes, the charger reconnects to your Wi-Fi and shows up in Home Assistant.

---

## The manual way (advanced / no Python)

If you'd rather do it by hand with `curl` (or any HTTP tool):

**1. Setup mode** — press and **hold the connector button ~10s** until the connectivity light
changes (orange/blinking); wait until the setup Wi-Fi `AP_FLO_xxxx` appears. (Red = not in AP
mode; re-do the hold.)

**2. Join** your laptop's Wi-Fi to **`AP_FLO_xxxx`** (password from the card/FLO). The charger is
at **`192.168.9.1`**. *(Tip: a wired LAN connection can stay up alongside so you keep internet.)*

**3. Read the current config** (safe):
```bash
curl http://192.168.9.1/onboarding/ocpp_status
curl http://192.168.9.1/onboarding/wifi_status
```
*(The charger ignores `ping`; use HTTP.)*

**4. Point it at your bridge** — ⚠ **body is snake_case** (camelCase returns HTTP 422):
```bash
curl -X PUT http://192.168.9.1/onboarding/ocpp_configuration \
  -H 'Content-Type: application/json' \
  -d '{"ocpp_url":"ws://<HOST-IP>:9000/flo","ocpp_username":"flo","ocpp_password":"flo"}'
```
`<HOST-IP>` = the bridge machine's LAN IP. Username/password can be anything (the bridge accepts
any charge point). The `/flo` path becomes the charge-point id in the logs — pick anything.

**5. Verify then finalize:**
```bash
curl http://192.168.9.1/onboarding/ocpp_status   # should show your URL, status CONNECTED
curl -X POST http://192.168.9.1/onboarding/exit
```

---

## Confirm it worked

In Home Assistant the "Flo Home X6" device comes alive (Status `Available`, telemetry when you
plug in). Bridge container logs show `Charger connected: /flo`.

## Revert to FLO cloud

Re-pair the charger with the **FLO app** (using the setup Wi-Fi creds) — it re-provisions the
original cloud OCPP config. (We overwrite the OCPP fields, so re-pairing is the clean restore;
there's no one-command undo.)

## Notes / gotchas

- `/onboarding/*` is served **only in setup (AP) mode** — on the charger's normal LAN IP it
  returns 502.
- The charger accepts plain **`ws://`** (no TLS needed).
- After WAN-blocking, expect a **slow reconnect** the next time the bridge restarts after a long
  outage — see the README's WAN-block note.
