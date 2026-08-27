"""
Test : start immediatement suivi d'un stop sans attendre la confirmation.
Simule un utilisateur qui appuie start puis stop rapidement dans HA.
"""
import time
from flo_client.auth import load_tokens, refresh_access_token, save_tokens
from flo_client.client import FloX6Client

tokens = load_tokens()
tokens = refresh_access_token(tokens["refresh_token"])
save_tokens(tokens)
client = FloX6Client(tokens["access_token"])

station = client.get_station()
uid = station["chargingStationUid"]
print(f"Statut initial : {station['evse']['status']}\n")

def get_evse_status():
    return client.get_station()["evse"]["status"]

def attendre_statut(statut_cible, timeout=90):
    debut = time.time()
    while time.time() - debut < timeout:
        s = get_evse_status()
        elapsed = time.time() - debut
        print(f"  [{elapsed:.0f}s] EVSE={s}")
        if s == statut_cible:
            return True, elapsed
        time.sleep(5)
    return False, timeout

# Etape 1 : s'assurer qu'on part de PluggedIn (stop si en charge)
if station["evse"]["status"] == "Charging":
    print("=== Preparation : stop pour partir de PluggedIn ===")
    client.stop_charge(uid)
    ok, t = attendre_statut("PluggedIn")
    print(f"Pret en PluggedIn ({t:.0f}s)\n")

# Etape 2 : START puis STOP immediat (2 secondes apres)
print("=== TEST : START puis STOP 2 secondes apres ===")
print("Envoi start...")
client.start_charge(uid, evse_id="1")
print("Attente 2 secondes...")
time.sleep(2)
print(f"Statut apres 2s : {get_evse_status()}")
print("Envoi stop MAINTENANT (avant confirmation du start)...")
ok = client.stop_charge(uid)
print(f"Commande stop : {'OK' if ok else 'ECHEC'}")

print("\nSurveillance du resultat...")
debut = time.time()
for i in range(12):
    s = get_evse_status()
    session = client.get_session()
    sess = session.get("sessionState") if session else "aucune"
    print(f"  [{time.time()-debut:.0f}s] EVSE={s}  session={sess}")
    time.sleep(5)

# Remise en charge finale
print(f"\n=== Remise en charge ===")
statut = get_evse_status()
if statut == "PluggedIn":
    client.start_charge(uid, evse_id="1")
    ok, t = attendre_statut("Charging")
    print(f"Remise en charge : {'OK' if ok else 'ECHEC'} ({t:.0f}s)")
elif statut == "Charging":
    print("Deja en charge - rien a faire.")
else:
    print(f"Statut inattendu : {statut} - verifie l'app.")
