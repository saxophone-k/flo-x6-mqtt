#!/usr/bin/env python3
"""
flo-x6-mqtt — charger repoint UI.

A friendly local web page to point your FLO Home X6 at your own server (or back to FLO).
Run it and your browser opens to the UI — no commands, no curl.

How it works: the browser can't call the charger's setup API directly (CORS), so this tool
runs a tiny local web server the browser talks to, and *it* relays to the charger. Stdlib
only — any Python 3, no pip install.
"""
import json
import threading
import time
import urllib.request
import urllib.error
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

CHARGER = "http://192.168.9.1"                       # charger address in setup (AP) mode
OCPP_PORT = 9000                                     # must match the bridge's FLO_OCPP_PORT
FLO_URL = "wss://ocpp.cloud.flo.ca/residential"      # FLO's cloud OCPP endpoint
UI_PORT = 8642

STATE = {"flo_username": None}   # remember the original FLO username for best-effort restore


def charger(method, path, body=None, timeout=8):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(CHARGER + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode(errors="replace")
        return resp.status, (json.loads(raw) if raw.strip().startswith("{") else {})


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FLO X6 — Local Setup</title>
<style>
  :root{--bg:#0f1720;--card:#1b2430;--fg:#e7edf3;--mut:#94a3b8;--acc:#39bd6b;--acc2:#3b82f6;--warn:#e8a400;--err:#ef4444;--line:#2b3644}
  *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,Segoe UI,Roboto,sans-serif}
  .wrap{max-width:560px;margin:0 auto;padding:24px}
  h1{font-size:22px;margin:8px 0 2px} .sub{color:var(--mut);margin:0 0 20px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px;margin:14px 0}
  .pill{display:inline-block;padding:3px 10px;border-radius:999px;font-size:13px;font-weight:600}
  .pill.flo{background:#3a2a12;color:#f0b64a} .pill.local{background:#123020;color:#5fd08a} .pill.off{background:#3a1616;color:#f08a8a}
  label{display:block;font-size:13px;color:var(--mut);margin:14px 0 6px}
  input{width:100%;padding:12px;border-radius:10px;border:1px solid var(--line);background:#0d141d;color:var(--fg);font-size:16px}
  button{border:0;border-radius:10px;padding:12px 16px;font-size:16px;font-weight:600;cursor:pointer;color:#fff}
  .primary{background:var(--acc)} .primary:hover{filter:brightness(1.08)}
  .blue{background:var(--acc2)} .ghost{background:#2a3543;color:var(--fg)} .warn{background:#5a4410;color:#f0c866}
  button:disabled{opacity:.5;cursor:default}
  .row{display:flex;gap:10px;flex-wrap:wrap} .row>*{flex:1}
  .muted{color:var(--mut);font-size:14px} .mono{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:13px;word-break:break-all}
  .msg{margin-top:14px;padding:12px;border-radius:10px;font-size:14px;display:none}
  .msg.show{display:block} .ok{background:#12301f;color:#7ee2a3;border:1px solid #1f6b42}
  .bad{background:#3a1616;color:#f4a3a3;border:1px solid #7a2b2b} .info{background:#12233a;color:#9cc4f0;border:1px solid #2b4d7a}
  .hr{height:1px;background:var(--line);margin:18px 0} details summary{cursor:pointer;color:var(--mut);font-size:14px}
  .steps{background:#0d141d;border:1px dashed var(--line);border-radius:10px;padding:14px;color:var(--mut);font-size:14px}
</style></head><body><div class="wrap">
  <h1>⚡ FLO Home X6 — Local Setup</h1>
  <p class="sub">Point your charger at your own server, instead of FLO's cloud.</p>

  <div class="card" id="statusCard">
    <div id="statusBody"><span class="muted">Checking the charger…</span></div>
  </div>

  <div class="card" id="applyCard" style="display:none">
    <label for="ip">Your server's IP address (the machine running flo-x6-mqtt)</label>
    <input id="ip" placeholder="e.g. 192.168.1.50" inputmode="decimal" autocomplete="off">
    <div class="muted" style="margin:8px 0 14px">Your charger will be pointed at
      <span class="mono">ws://&lt;that IP&gt;:9000/flo</span></div>
    <button class="primary" style="width:100%" id="applyBtn" onclick="apply()">Point charger at my server</button>
    <div class="hr"></div>
    <details><summary>Put it back to FLO cloud (e.g. before reselling)</summary>
      <p class="muted" style="margin-top:12px">This writes FLO's server address back. For a full
        reset / re-linking to a FLO account, use the <b>FLO app → Unpair Station</b> — that's the
        clean way to hand the charger to a new owner.</p>
      <button class="warn" style="width:100%" id="restoreBtn" onclick="restore()">Restore FLO cloud address</button>
    </details>
    <div class="msg" id="msg"></div>
    <div id="doneBox" style="display:none;margin-top:14px">
      <button class="blue" style="width:100%" onclick="finish()">Finish &amp; close setup mode</button>
    </div>
  </div>

  <div class="card" id="helpCard" style="display:none">
    <div class="steps" id="helpBody"></div>
    <button class="ghost" style="width:100%;margin-top:12px" onclick="loadStatus()">Retry</button>
  </div>
</div>
<script>
const $=s=>document.querySelector(s);
function show(el,cls,txt){el.className='msg show '+cls;el.textContent=txt}
async function api(path,opts){const r=await fetch(path,opts);return r.json()}

async function loadStatus(){
  $('#helpCard').style.display='none';
  $('#statusBody').innerHTML='<span class="muted">Checking the charger…</span>';
  let d; try{ d=await api('/api/status'); }catch(e){ d={ok:false,error:String(e)}; }
  if(!d.ok){
    $('#statusBody').innerHTML='<span class="pill off">Not reachable</span>';
    $('#applyCard').style.display='none';
    $('#helpBody').innerHTML=
      '<b>Can\'t reach the charger.</b><br><br>1. Put the charger in <b>setup mode</b>: press and '
      +'hold the connector button ~10s until the small light turns orange / blinks and the '
      +'<b>AP_FLO_xxxx</b> Wi-Fi appears.<br><br>2. Connect <b>this computer\'s Wi-Fi</b> to '
      +'<b>AP_FLO_xxxx</b> (password on the card from the box).<br><br>3. Then press Retry.';
    $('#helpCard').style.display='block';
    return;
  }
  const url=(d.ocpp&&d.ocpp.ocpp_url)||'';
  const isFlo=d.is_flo, st=(d.ocpp&&d.ocpp.status)||'';
  let pill = isFlo?'<span class="pill flo">FLO cloud</span>'
                  :'<span class="pill local">Your server</span>';
  $('#statusBody').innerHTML = 'Currently configured for: '+pill
    +'<div class="mono" style="margin-top:10px">'+ (url||'(unknown)') +'</div>'
    + (st?'<div class="muted" style="margin-top:6px">Link status: '+st+'</div>':'');
  $('#applyCard').style.display='block';
}
async function apply(){
  const ip=$('#ip').value.trim();
  const m=$('#msg');
  if(!ip){show(m,'bad','Please enter your server\'s IP address.');return}
  $('#applyBtn').disabled=true; show(m,'info','Applying… pointing the charger at your server.');
  const d=await api('/api/apply',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ip})});
  $('#applyBtn').disabled=false;
  if(d.ok){show(m,'ok','✓ Done. Charger now points at '+d.url+(d.status?'  (status: '+d.status+')':'')
    +'. Click below to finish.');$('#doneBox').style.display='block';}
  else show(m,'bad','✗ '+(d.error||'Failed.'));
}
async function restore(){
  const m=$('#msg'); $('#restoreBtn').disabled=true; show(m,'info','Restoring FLO cloud address…');
  const d=await api('/api/restore',{method:'POST'}); $('#restoreBtn').disabled=false;
  if(d.ok){show(m,'ok','✓ FLO cloud address written back.'+(d.known_user?'':
    ' Note: the original FLO password can\'t be recovered — if it doesn\'t reconnect to FLO, use the FLO app to re-pair / Unpair Station.')
    +' Click below to finish.');$('#doneBox').style.display='block';}
  else show(m,'bad','✗ '+(d.error||'Failed.'));
}
async function finish(){
  const m=$('#msg'); show(m,'info','Closing setup mode…');
  await api('/api/exit',{method:'POST'});
  show(m,'ok','✓ Setup mode closed. The charger will reconnect to your Wi-Fi. '
    +'Check Home Assistant — the Flo Home X6 device should come online shortly. You can close this page.');
}
loadStatus();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            return self._send(200, PAGE, "text/html; charset=utf-8")
        if self.path == "/api/status":
            return self._status()
        self._send(404, "{}")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(n).decode() if n else ""
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {}
        if self.path == "/api/apply":
            return self._apply(payload)
        if self.path == "/api/restore":
            return self._restore()
        if self.path == "/api/exit":
            return self._exit()
        self._send(404, "{}")

    def _status(self):
        try:
            _, data = charger("GET", "/onboarding/ocpp_status")
            url = data.get("ocpp_url", "")
            if "flo.ca" in url and data.get("ocpp_username"):
                STATE["flo_username"] = data["ocpp_username"]
            wifi = None
            try:
                _, wifi = charger("GET", "/onboarding/wifi_status")
            except Exception:
                pass
            self._send(200, json.dumps({"ok": True, "ocpp": data, "wifi": wifi,
                                        "is_flo": "flo.ca" in url}))
        except Exception as e:
            self._send(200, json.dumps({"ok": False, "error": str(e)}))

    def _apply(self, payload):
        ip = (payload.get("ip") or "").strip()
        if not ip:
            return self._send(200, json.dumps({"ok": False, "error": "No IP address given."}))
        url = f"ws://{ip}:{OCPP_PORT}/flo"
        try:
            st, _ = charger("PUT", "/onboarding/ocpp_configuration",
                            {"ocpp_url": url, "ocpp_username": "flo", "ocpp_password": "flo"})
            if st != 200:
                return self._send(200, json.dumps({"ok": False, "error": f"Charger rejected (HTTP {st})."}))
            time.sleep(2)
            _, data = charger("GET", "/onboarding/ocpp_status")
            self._send(200, json.dumps({"ok": True, "url": url, "status": data.get("status")}))
        except urllib.error.HTTPError as e:
            self._send(200, json.dumps({"ok": False, "error": f"Charger rejected (HTTP {e.code})."}))
        except Exception as e:
            self._send(200, json.dumps({"ok": False, "error": str(e)}))

    def _restore(self):
        user = STATE.get("flo_username")
        try:
            st, _ = charger("PUT", "/onboarding/ocpp_configuration",
                            {"ocpp_url": FLO_URL, "ocpp_username": user or "flo", "ocpp_password": "flo"})
            self._send(200, json.dumps({"ok": st == 200, "url": FLO_URL, "known_user": bool(user)}))
        except urllib.error.HTTPError as e:
            self._send(200, json.dumps({"ok": False, "error": f"Charger rejected (HTTP {e.code})."}))
        except Exception as e:
            self._send(200, json.dumps({"ok": False, "error": str(e)}))

    def _exit(self):
        try:
            charger("POST", "/onboarding/exit")
        except Exception:
            pass
        self._send(200, json.dumps({"ok": True}))


def main():
    srv = HTTPServer(("127.0.0.1", UI_PORT), Handler)
    url = f"http://127.0.0.1:{UI_PORT}/"
    print("=" * 56)
    print("  FLO X6 local setup — opening in your browser:")
    print(f"    {url}")
    print("  (If it doesn't open, paste that address into your browser.)")
    print("  Leave this window open; close it when you're done.")
    print("=" * 56)
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
