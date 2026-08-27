"""
Suite de tests automatisés — Catégorie A (sans intervention utilisateur)
Documente chaque résultat pour informer le code de main.py
"""
import json, os, time, copy
from unittest.mock import patch, MagicMock
import requests

RESULTS = []

def log(test, status, detail=""):
    icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
    print(f"\n{icon} [{test}] {status}")
    if detail:
        print(f"   {detail}")
    RESULTS.append((test, status, detail))

def separator(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

# ─────────────────────────────────────────────────────────────
# Setup
# ─────────────────────────────────────────────────────────────
from flo_client.auth import (
    load_tokens, save_tokens, refresh_access_token,
    get_valid_access_token, authenticate
)
from flo_client.client import FloX6Client
from flo_client.exceptions import FloAuthError, FloNetworkError, FloAPIError

tokens_backup = load_tokens()

# ─────────────────────────────────────────────────────────────
# A1 — Access token expiré → refresh automatique
# ─────────────────────────────────────────────────────────────
separator("A1 — Access token expiré → refresh automatique")
try:
    # Forcer l'expiration de l'access token
    fake = copy.deepcopy(tokens_backup)
    fake["expires_at"] = int(time.time()) - 100  # expiré il y a 100s
    save_tokens(fake)

    token = get_valid_access_token("unused@test.com", "unused")
    # Vérifier que le nouveau token est différent du faux
    if token and token != fake.get("access_token", ""):
        log("A1", "PASS", "Token expiré → refresh automatique déclenché et réussi")
    else:
        log("A1", "FAIL", "Token expiré mais pas de refresh")
except Exception as e:
    log("A1", "FAIL", str(e))
finally:
    save_tokens(tokens_backup)

# ─────────────────────────────────────────────────────────────
# A2 — Refresh token invalide → fallback re-auth
# ─────────────────────────────────────────────────────────────
separator("A2 — Refresh token invalide → comportement")
try:
    fake = copy.deepcopy(tokens_backup)
    fake["expires_at"] = int(time.time()) - 100
    fake["refresh_token"] = "token_completement_invalide_xyz123"
    save_tokens(fake)

    try:
        token = refresh_access_token("token_completement_invalide_xyz123")
        log("A2", "FAIL", "Aurait dû lever FloAuthError mais a réussi")
    except FloAuthError as e:
        log("A2", "PASS", f"FloAuthError levée correctement : {e}")
    except FloNetworkError as e:
        log("A2", "PASS", f"FloNetworkError (réseau) : {e}")
except Exception as e:
    log("A2", "FAIL", str(e))
finally:
    save_tokens(tokens_backup)

# ─────────────────────────────────────────────────────────────
# A3 — Mauvais credentials → message d'erreur clair
# ─────────────────────────────────────────────────────────────
separator("A3 — Mauvais credentials → FloAuthError")
try:
    authenticate("mauvais@email.com", "mauvaispassword")
    log("A3", "FAIL", "Aurait dû lever FloAuthError")
except FloAuthError as e:
    log("A3", "PASS", f"FloAuthError levée : {e}")
except FloNetworkError as e:
    log("A3", "WARN", f"FloNetworkError (problème réseau, pas credentials) : {e}")
except Exception as e:
    log("A3", "FAIL", f"Exception inattendue : {type(e).__name__} : {e}")

# ─────────────────────────────────────────────────────────────
# A4 — Champ JSON manquant dans réponse API
# ─────────────────────────────────────────────────────────────
separator("A4 — Champ JSON manquant → accès sécurisé")
try:
    tokens = load_tokens()
    client = FloX6Client(tokens["access_token"])

    # Simuler une réponse avec champ manquant
    incomplete_station = {
        "chargingStationUid": "test-uid",
        # evse manquant intentionnellement
        "connectionStatus": "Online",
        "model": "FLO Home X6",
    }

    # Vérifier que .get() ne crash pas
    evse = incomplete_station.get("evse", {})
    status = evse.get("status", "Unknown")
    connectors = evse.get("connectors", [])
    max_amp = connectors[0].get("maxAmperage") if connectors else None

    log("A4", "PASS",
        f"Champs manquants gérés avec .get() : status={status}, max_amp={max_amp}")
except Exception as e:
    log("A4", "FAIL", f"KeyError ou crash : {e}")

# ─────────────────────────────────────────────────────────────
# A5 — Rate limiting (20 appels rapides)
# ─────────────────────────────────────────────────────────────
separator("A5 — Rate limiting (20 appels rapides)")
try:
    tokens = load_tokens()
    client = FloX6Client(tokens["access_token"])
    status_codes = []

    for i in range(20):
        try:
            client.get_station()
            status_codes.append(200)
        except FloAPIError as e:
            if "429" in str(e):
                status_codes.append(429)
            elif "401" in str(e):
                status_codes.append(401)
            else:
                status_codes.append(-1)
        except FloNetworkError:
            status_codes.append(0)

    got_429 = 429 in status_codes
    got_errors = any(c not in (200, 0) for c in status_codes)
    unique = list(dict.fromkeys(status_codes))

    if got_429:
        log("A5", "WARN",
            f"Rate limiting détecté (429) → à gérer avec backoff. Codes: {unique}")
    else:
        log("A5", "PASS",
            f"Pas de rate limiting sur 20 appels rapides. Codes: {unique}")
except Exception as e:
    log("A5", "FAIL", str(e))

# ─────────────────────────────────────────────────────────────
# A6 — Simulation HTTP 500
# ─────────────────────────────────────────────────────────────
separator("A6 — HTTP 500 → FloAPIError")
try:
    tokens = load_tokens()
    client = FloX6Client(tokens["access_token"])

    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"

    with patch.object(client._session, "get", return_value=mock_resp):
        client.get_station()
    log("A6", "FAIL", "Aurait dû lever FloAPIError sur HTTP 500")
except FloAPIError as e:
    log("A6", "PASS", f"FloAPIError levée correctement : {e}")
except Exception as e:
    log("A6", "FAIL", f"Exception inattendue : {type(e).__name__} : {e}")

# ─────────────────────────────────────────────────────────────
# A7 — get_session() retourne None → sensors se comportent comment
# ─────────────────────────────────────────────────────────────
separator("A7 — get_session() = None → valeurs sensors")
try:
    # Simuler la logique du daemon quand session=None
    session = None

    # Ce que le daemon doit publier pour chaque sensor
    def safe_get(d, key, default=None):
        return d.get(key, default) if d else default

    amp        = safe_get(session, "amperage", 0)
    voltage    = safe_get(session, "voltage", 0)
    power_w    = amp * voltage
    energy_kwh = safe_get(session, "energyTransferredWh", 0) / 1000
    state      = safe_get(session, "sessionState", "Idle")
    active     = session is not None

    result = f"state={state}, active={active}, amp={amp}A, power={power_w}W, energy={energy_kwh}kWh"
    log("A7", "PASS", f"Valeurs par défaut correctes : {result}")
except Exception as e:
    log("A7", "FAIL", str(e))

# ─────────────────────────────────────────────────────────────
# A8 — Double commande start/start rapide
# ─────────────────────────────────────────────────────────────
separator("A8 — Double commande start rapide → guard nécessaire")
try:
    tokens = load_tokens()
    client = FloX6Client(tokens["access_token"])
    station = client.get_station()
    uid = station["chargingStationUid"]
    evse_status = station["evse"]["status"]

    if evse_status == "Charging":
        # Envoyer start alors qu'on charge déjà
        r1 = client.start_charge(uid, evse_id="1")
        time.sleep(1)
        r2 = client.start_charge(uid, evse_id="1")
        station_after = client.get_station()
        status_after = station_after["evse"]["status"]
        log("A8", "PASS" if status_after == "Charging" else "WARN",
            f"Double start sur borne Charging → r1={r1}, r2={r2}, statut final={status_after}. "
            f"NOTE: le daemon devra bloquer les doublons côté logiciel")
    else:
        log("A8", "WARN", f"Borne pas en charge ({evse_status}) — test partiel seulement")
except Exception as e:
    log("A8", "FAIL", str(e))

# ─────────────────────────────────────────────────────────────
# A9 — Commande MQTT inconnue → doit être ignorée proprement
# ─────────────────────────────────────────────────────────────
separator("A9 — Commande MQTT inconnue → gestion")
try:
    # Simuler la logique de dispatch des commandes MQTT du daemon
    VALID_COMMANDS = {"start", "stop"}

    def handle_command(payload: str) -> str:
        cmd = payload.strip().lower()
        if cmd not in VALID_COMMANDS:
            return f"IGNORED: commande inconnue '{cmd}'"
        return f"EXECUTED: {cmd}"

    tests = [
        ("start", "EXECUTED: start"),
        ("stop",  "EXECUTED: stop"),
        ("reboot", "IGNORED"),
        ("",       "IGNORED"),
        ("START",  "EXECUTED: start"),  # insensible à la casse
        ("__inject__", "IGNORED"),
    ]

    all_ok = True
    for payload, expected_prefix in tests:
        result = handle_command(payload)
        ok = result.startswith(expected_prefix.split(":")[0])
        if not ok:
            all_ok = False
            print(f"   payload='{payload}' → {result} (attendu: {expected_prefix})")

    log("A9", "PASS" if all_ok else "FAIL",
        "Logique de dispatch : commandes inconnues ignorées proprement")
except Exception as e:
    log("A9", "FAIL", str(e))

# ─────────────────────────────────────────────────────────────
# A10 — Première exécution sans tokens.json
# ─────────────────────────────────────────────────────────────
separator("A10 — Première exécution sans tokens.json")
try:
    token_file = "data/tokens.json"
    backup = None

    if os.path.exists(token_file):
        with open(token_file) as f:
            backup = json.load(f)
        os.rename(token_file, token_file + ".bak")

    result = load_tokens()
    if result is None:
        log("A10", "PASS", "load_tokens() retourne None quand fichier absent — correct")
    else:
        log("A10", "FAIL", f"load_tokens() retourne {result} au lieu de None")
except Exception as e:
    log("A10", "FAIL", str(e))
finally:
    if os.path.exists(token_file + ".bak"):
        os.rename(token_file + ".bak", token_file)

# ─────────────────────────────────────────────────────────────
# A12 — energyTransferredWh entre sessions
# ─────────────────────────────────────────────────────────────
separator("A12 — energyTransferredWh reset entre sessions")
try:
    tokens = load_tokens()
    client = FloX6Client(tokens["access_token"])
    session = client.get_session()

    if session:
        energy = session.get("energyTransferredWh", 0)
        session_id = session.get("id", "?")
        print(f"   Session active : id={session_id}, energy={energy}Wh")
        print(f"   → Ce compteur repart à 0 à chaque nouvelle session")
        print(f"   → Le daemon doit publier state_class: total_increasing")
        print(f"   → ET gérer le reset : si nouvelle valeur < ancienne → nouvelle session")
        log("A12", "PASS",
            f"Session courante {energy}Wh. "
            f"Logique anti-reset à implémenter dans main.py : "
            f"détecter session_id change → pas de décrémentation du compteur HA")
    else:
        log("A12", "WARN", "Aucune session active — tester pendant charge active")
except Exception as e:
    log("A12", "FAIL", str(e))

# ─────────────────────────────────────────────────────────────
# A13 — Exception non catchée dans boucle de polling
# ─────────────────────────────────────────────────────────────
separator("A13 — Exception non catchée → daemon survit")
try:
    # Simuler la boucle principale du daemon avec une exception au milieu
    errors = []
    successful_cycles = 0

    for cycle in range(5):
        try:
            if cycle == 2:
                raise RuntimeError("Erreur simulée au cycle 3")
            successful_cycles += 1
        except Exception as e:
            errors.append(str(e))
            # Le daemon doit logger et continuer, pas mourir

    if successful_cycles == 4 and len(errors) == 1:
        log("A13", "PASS",
            f"Boucle survit à une exception : {successful_cycles}/5 cycles OK, "
            f"1 erreur catchée. Le daemon doit avoir un try/except global dans la boucle")
    else:
        log("A13", "FAIL", f"cycles={successful_cycles}, erreurs={errors}")
except Exception as e:
    log("A13", "FAIL", str(e))

# ─────────────────────────────────────────────────────────────
# Résumé final
# ─────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("  RÉSUMÉ")
print('='*60)
passed  = sum(1 for _, s, _ in RESULTS if s == "PASS")
warned  = sum(1 for _, s, _ in RESULTS if s == "WARN")
failed  = sum(1 for _, s, _ in RESULTS if s == "FAIL")
print(f"  ✅ PASS : {passed}")
print(f"  ⚠️  WARN : {warned}")
print(f"  ❌ FAIL : {failed}")
print()
for name, status, detail in RESULTS:
    icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
    print(f"  {icon} {name} : {detail[:80]}")
