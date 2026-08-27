import time
from flo_client.auth import load_tokens, refresh_access_token, save_tokens
from flo_client.client import FloX6Client

tokens = load_tokens()
tokens = refresh_access_token(tokens["refresh_token"])
save_tokens(tokens)
client = FloX6Client(tokens["access_token"])
print("Token OK - surveillance lastRefreshMs sur 3 minutes (36 appels x 5s)\n")

last_refresh_ms = None
changes = []
start = time.time()

for i in range(36):
    session = client.get_session()

    if not session:
        print(f"[{i+1:02d}] Aucune session active")
        time.sleep(5)
        continue

    ms = session.get("lastRefreshMs", 0)
    amp = session.get("amperage", 0)
    energy = session.get("energyTransferredWh", 0)
    elapsed = time.time() - start

    changed = "<-- CHANGE" if last_refresh_ms and ms != last_refresh_ms else ""
    if changed:
        changes.append(elapsed)

    print(f"[{i+1:02d}] t={elapsed:5.0f}s  lastRefreshMs={ms}  {amp}A  {energy:.1f}Wh  {changed}")
    last_refresh_ms = ms
    time.sleep(5)

print(f"\n{'='*60}")
print(f"Changements detectes : {len(changes)}")
if len(changes) >= 2:
    intervals = [changes[j] - changes[j-1] for j in range(1, len(changes))]
    print(f"Intervalles entre changements : {[f'{x:.0f}s' for x in intervals]}")
    print(f"Intervalle moyen reel de rapport : ~{sum(intervals)/len(intervals):.0f} secondes")
elif len(changes) == 1:
    print("Un seul changement detecte - relancer le test plus longtemps")
else:
    print("Aucun changement - lastRefreshMs ne se met pas a jour (event-driven?)")
