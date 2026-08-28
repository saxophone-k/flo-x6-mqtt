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

## The easy way — the setup UI (recommended)

Do these **in order**. Steps 1–2 need internet; from step 3 on you'll be on the charger's own
Wi-Fi (which has **no internet** — that's normal and expected).

> This assumes your charger is **already working on your home Wi-Fi** (i.e. it's been running on
> FLO's app). We only change *which server it reports to* — we leave your Wi-Fi settings alone.

### 1 · Install Python 3 *(one time, needs internet)*
- **macOS / Linux:** you almost certainly already have it.
- **Windows:** install from **[python.org/downloads](https://www.python.org/downloads/)** and,
  during install, **tick "Add Python to PATH"** (important).

### 2 · Download the helper *(needs internet — do it now)*
Download **`repoint_ui.py`** from this repo (open the file → **Download raw**) and save it
somewhere easy, like your Desktop. Get this now, before you go offline in the next step.

### 3 · Put the charger in pairing mode
On the charger, **press and HOLD the button on the charging connector (the "gun") for 10+
seconds** — keep holding until the charger's **own Wi-Fi network, `AP_FLO_xxxx`, appears in your
laptop's Wi-Fi list.** (The small connectivity light changes — orange / blinking.) This pairing
mode is the **only** window in which the setup works — it's the door we walk through.

### 4 · Join the charger's Wi-Fi
On your laptop, open the Wi-Fi menu and **connect to `AP_FLO_xxxx`** (password is on the pairing
card from the box; lost it? FLO support can give it to you for your serial). **Your laptop loses
internet now — that's fine, you already downloaded everything.**

### 5 · Run the helper
- **Windows:** **double-click `repoint_ui.py`** → a small black window opens (the helper — leave
  it open) and your **browser opens automatically** to the setup page.
- **macOS / Linux:** in **Terminal**, `python3 repoint_ui.py` → the browser opens to the page.

*(That little window is just the helper running on your computer — you only look at the browser.)*

### 6 · Point it at your server
The page shows **"Currently configured for: FLO cloud."** Type your **server's IP address** (the
machine running the bridge), click **Point charger at my server**, then click **Finish**.

### 7 · Done — put your laptop back
The charger **automatically leaves pairing mode and stays on your home Wi-Fi** (it was connected
to it the whole time) — now reporting to *your* bridge instead of FLO. **You don't reconfigure
the charger's Wi-Fi.** The only thing left for you: **reconnect your laptop's Wi-Fi to your normal
home network.** Then open Home Assistant — the "Flo Home X6" device comes online (plug in the car
to see live data).

*(Prefer not to run a script at all? The page also has a **Restore FLO cloud** option for
reselling — and there's a `curl` recipe below.)*

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
