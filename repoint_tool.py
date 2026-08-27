#!/usr/bin/env python3
"""
flo-x6-mqtt — charger repoint helper.

Points your FLO Home X6 at your own local server instead of FLO's cloud.
Friendly + guided — no commands to type. Just answer the prompts.

Run it:  python repoint_tool.py     (or double-click the packaged version)
"""
import json
import sys
import time
import urllib.request
import urllib.error

CHARGER = "http://192.168.9.1"          # the charger's address in setup (AP) mode
OCPP_PORT = 9000                         # must match the bridge's FLO_OCPP_PORT


def _req(method, path, body=None, timeout=8):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(CHARGER + path, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        raw = resp.read().decode(errors="replace")
        return resp.status, (json.loads(raw) if raw.strip().startswith("{") else raw)


def ask(prompt):
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled."); sys.exit(1)


def pause(prompt):
    try:
        input(prompt)
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled."); sys.exit(1)


def reachable():
    try:
        _req("GET", "/onboarding/ocpp_status", timeout=5)
        return True
    except Exception:
        return False


def main():
    print("""
========================================================
  FLO Home X6  →  local server  (repoint helper)
========================================================
This makes your charger talk to YOUR home server instead
of FLO's cloud. It's reversible (re-pair with the FLO app).

You'll do two things by hand, then I'll do the rest.
""")

    # --- Step 1: AP mode ---
    print("STEP 1 — Put the charger in setup mode:")
    print("  • Press and HOLD the button on the charging connector ~10 seconds,")
    print("    until the small connectivity light changes (orange / blinking).")
    print("  • Wait until it settles and the setup Wi-Fi 'AP_FLO_xxxx' appears.\n")
    pause("  Press Enter once the setup light is on… ")

    # --- Step 2: join AP ---
    print("\nSTEP 2 — Connect THIS computer's Wi-Fi to the charger:")
    print("  • Open your Wi-Fi menu and join the network named 'AP_FLO_xxxx'.")
    print("  • Its password is on the pairing card from the box")
    print("    (lost it? FLO support can give it to you for your serial).\n")
    pause("  Press Enter once you're connected to AP_FLO_xxxx… ")

    # --- verify we can reach the charger ---
    print("\nChecking I can reach the charger…")
    for attempt in range(3):
        if reachable():
            break
        print("  ✗ Can't reach the charger at 192.168.9.1.")
        print("    Make sure your Wi-Fi is connected to 'AP_FLO_xxxx' (not your home Wi-Fi).")
        if ask("    Try again? (y/n) ").lower() != "y":
            print("Aborted — no changes made."); sys.exit(1)
    else:
        print("Still can't reach it. Aborted — no changes made."); sys.exit(1)

    # --- show current config ---
    try:
        _, cur = _req("GET", "/onboarding/ocpp_status")
        print("\n  ✓ Reached the charger.")
        if isinstance(cur, dict):
            print(f"    Currently pointed at: {cur.get('ocpp_url')}  (status: {cur.get('status')})")
    except Exception as e:
        print(f"  (couldn't read current config: {e})")

    # --- get the bridge address ---
    print("\nSTEP 3 — Where is your local server (the flo-x6-mqtt bridge)?")
    print("  Enter the IP address of the machine running it (e.g. 192.168.1.50).")
    ip = ask("  Bridge IP address: ")
    if not ip:
        print("No address given. Aborted."); sys.exit(1)
    url = f"ws://{ip}:{OCPP_PORT}/flo"
    print(f"\n  I will point your charger at:  {url}")
    if ask("  Proceed? (y/n) ").lower() != "y":
        print("Aborted — no changes made."); sys.exit(1)

    # --- write it ---
    try:
        st, _ = _req("PUT", "/onboarding/ocpp_configuration",
                     {"ocpp_url": url, "ocpp_username": "flo", "ocpp_password": "flo"})
        if st != 200:
            print(f"  ✗ The charger rejected the change (HTTP {st}). Aborted."); sys.exit(1)
    except urllib.error.HTTPError as e:
        print(f"  ✗ The charger rejected the change (HTTP {e.code}). Aborted."); sys.exit(1)
    except Exception as e:
        print(f"  ✗ Failed to send the change: {e}. Aborted."); sys.exit(1)

    print("  ✓ Sent. Checking the charger accepted it…")
    time.sleep(3)
    try:
        _, s = _req("GET", "/onboarding/ocpp_status")
        if isinstance(s, dict):
            print(f"    Now pointed at: {s.get('ocpp_url')}  (status: {s.get('status')})")
    except Exception:
        pass

    # --- finalize ---
    try:
        _req("POST", "/onboarding/exit")
    except Exception:
        pass

    print(f"""
========================================================
  ✓ Done! Your charger is now pointed at your server.
========================================================
It will leave setup mode and reconnect to your home Wi-Fi,
then connect to the bridge at {url}.

Next: in Home Assistant, the "Flo Home X6" device should
come online (plug in the car to see live data).

To undo this later: re-pair the charger with the FLO app.
""")
    pause("Press Enter to close… ")


if __name__ == "__main__":
    main()
