"""
Script de debug — affiche l'état brut complet de la borne Flo X6.

Usage :
  FLO_USERNAME=ton@email.com FLO_PASSWORD=tonmotdepasse python3 debug.py

Ou avec un fichier .env :
  python3 debug.py
"""

import json
import logging
import os
import sys

# Activer les logs détaillés pour voir chaque étape de l'auth
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s : %(message)s",
    stream=sys.stdout,
)

from flo_client.auth import get_valid_access_token
from flo_client.client import FloX6Client
from flo_client.connectivity import check_internet, check_flo_api
from flo_client.exceptions import FloAuthError, FloNetworkError, FloAPIError


def main():
    username = os.environ.get("FLO_USERNAME", "")
    password = os.environ.get("FLO_PASSWORD", "")

    if not username or not password:
        print("\n❌ Manque les credentials !")
        print("Lance avec :")
        print('  FLO_USERNAME="ton@email.com" FLO_PASSWORD="tonmotdepasse" python3 debug.py')
        sys.exit(1)

    # --- Vérification connectivité ---
    print("\n=== CONNECTIVITÉ ===")
    internet = check_internet()
    print(f"Internet    : {'✅ OK' if internet else '❌ DOWN'}")
    if not internet:
        print("Impossible de continuer sans internet.")
        sys.exit(1)

    flo_ok = check_flo_api()
    print(f"Cloud Flo   : {'✅ OK' if flo_ok else '❌ DOWN'}")
    if not flo_ok:
        print("Impossible de continuer — cloud Flo inaccessible.")
        sys.exit(1)

    # --- Authentification ---
    print("\n=== AUTHENTIFICATION ===")
    try:
        token = get_valid_access_token(username, password)
        print("✅ Token obtenu.")
    except FloAuthError as e:
        print(f"❌ Erreur auth : {e}")
        sys.exit(1)
    except FloNetworkError as e:
        print(f"❌ Erreur réseau : {e}")
        sys.exit(1)

    client = FloX6Client(token)

    # --- État de la borne ---
    print("\n=== ÉTAT DE LA BORNE ===")
    try:
        station = client.get_station()
        print(json.dumps(station, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"❌ Erreur get_station : {e}")

    # --- Session active ---
    print("\n=== SESSION ACTIVE ===")
    try:
        session = client.get_session()
        if session:
            print(json.dumps(session, indent=2, ensure_ascii=False))
        else:
            print("Aucune session active en ce moment.")
    except Exception as e:
        print(f"❌ Erreur get_session : {e}")

    # --- Résumé lisible ---
    print("\n=== RÉSUMÉ ===")
    try:
        uid  = station.get("chargingStationUid", "?")
        evse = station.get("evse", {})
        prefs = station.get("stationPreferences", {})
        print(f"UID            : {uid}")
        print(f"Modèle         : {station.get('modelType', station.get('homeModelType', '?'))} / {station.get('model', '?')}")
        print(f"Firmware       : {station.get('firmwareVersion', '?')}")
        print(f"Surnom         : {prefs.get('nickname', '?')}")
        print(f"Statut EVSE    : {evse.get('status', '?')}")
        print(f"Connexion      : {station.get('connectionStatus', '?')}")

        print(f"Puissance max  : {station.get('maxOutput', '?')} A")
        connectors = evse.get("connectors", [])
        if connectors:
            c = connectors[0]
            print(f"Ampérage max   : {c.get('maxAmperage', '?')} A")
            if c.get("maxVoltage"):
                print(f"Tension max    : {c.get('maxVoltage')} V")

        if session:
            power_w = session.get("amperage", 0) * session.get("voltage", 0)
            energy_kwh = session.get("energyTransferredWh", 0) / 1000
            print(f"\nSession active :")
            print(f"  État         : {session.get('sessionState', '?')}")
            print(f"  Ampérage     : {session.get('amperage', 0):.1f} A")
            print(f"  Tension      : {session.get('voltage', 0):.1f} V")
            print(f"  Puissance    : {power_w:.0f} W ({power_w/1000:.2f} kW)")
            print(f"  Énergie      : {energy_kwh:.3f} kWh")
            cost = session.get("cost", {})
            print(f"  Coût estimé  : {cost.get('estimatedCost', 0):.2f} {cost.get('currency', '')}")
    except Exception as e:
        print(f"Erreur résumé : {e}")


if __name__ == "__main__":
    main()
