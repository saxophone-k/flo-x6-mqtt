# PROGRESS — flo-x6-mqtt

Projet : Bridge Flo X6 → MQTT → Home Assistant
Démarré : 2026-05-15
Complété : 2026-05-18

Repo : https://github.com/saxophone-k/flo-x6-mqtt
Image : ghcr.io/saxophone-k/flo-x6-mqtt:latest (amd64 + arm64)

---

## PHASE 1 ✅ — Setup environnement

- apktool 2.7.0, jadx 1.5.0, mitmproxy 8.1.1, docker 29.1.3, python3 3.12.3
- Structure du projet créée

---

## PHASE 2 ✅ — Analyse statique APK

- APK : com.addenergie.reseauver v3.4.20
- 24 646 fichiers Java décompilés avec jadx
- API Base URL : https://emobility.flo.ca/
- Auth : PingIdentity OAuth2 PKCE (auth.pingone.ca)
- Environment ID : 6cedc65f-98e2-4651-bdb8-88ee4936c9ba
- Application ID : a52eedc6-7bcc-4d35-a57a-ef2685bd8101
- Tous les endpoints et modèles de données documentés
- Docs : API_ANALYSIS.md, ENTITIES_DISCOVERED.md

---

## PHASE 3 ✅ — Interception réseau (laptop Windows)

- SSL pinning iOS contourné → APK patché avec apk-mitm
- Émulateur Android Pixel 4 sur Windows (8-16 Go RAM)
- Station UID : 600a3f7d-30ba-4d67-bd4a-8d72e6286666
- Modèle : FLO Home X6, firmware 3.0.0, 48A max
- Body start session confirmé : {"evseId":"1"}
- Endpoint bonus découvert : fast-status-update

---

## PHASE 4 ✅ — Client Python Flo X6

- flo_client/auth.py — OAuth2 PKCE, refresh auto, cache tokens
- flo_client/client.py — get_station(), get_session(), start/stop, fast_status_update()
- flo_client/connectivity.py — check_internet(), check_flo_api()
- flo_client/exceptions.py — FloAuthError, FloNetworkError, FloAPIError
- debug.py — affichage état brut complet
- Testé avec vrais credentials → succès

---

## PHASE 5 ✅ — Daemon MQTT + Home Assistant Discovery

- main.py — boucle polling adaptative (30s/60s/120s)
- 24 entités MQTT Discovery
- LWT, availability online/offline, reconnexion auto
- Retry infini au démarrage si broker absent
- Guard commandes start/stop (délais mesurés)
- Client ID MQTT unique basé sur UID borne

---

## PHASE 5.5 ✅ — Tests d'intégration

### Tests automatisés (12/12 PASS)
A1-A13 : token refresh, credentials, JSON manquant, rate limiting, HTTP 500, session None, double commande, MQTT inconnu, première exécution, reset kWh, exception boucle

### Tests manuels (7/10 validés)
- B1 — Internet down → unavailable après ~3 min ✅
- B2 — Cloud Flo bloqué → unavailable après ~3 min ✅
- B3 — Broker MQTT tombe → reconnexion ~5s ✅
- B4 — Broker éteint au démarrage → retry 5→30s ✅
- B5 — Reconnexion après panne → validé avec B2 ✅
- B7 — Câble débranché → EVSE Available après ~30s ✅
- B10 — kill -9 → LWT instantané ✅

### Mesures empiriques (zéro suppositions)
- Fréquence rapport borne : 30 secondes exactes
- Délai confirmation stop : ~5 secondes
- Délai confirmation start : 2–16 secondes
- Délai requis stop→start : attendre PluggedIn
- Délai requis start→stop : aucun

---

## PHASE 6 ✅ — Docker & GitHub

- Dockerfile (python:3.11-slim)
- docker-compose.yml
- GitHub Actions : build amd64+arm64, push ghcr.io sur push main
- README.md complet
- github.com/saxophone-k/flo-x6-mqtt

---

## PHASE 7 ✅ — TrueNAS SCALE

- Image ghcr.io/saxophone-k/flo-x6-mqtt:latest
- Always pull image (mises à jour auto via GitHub)
- Volume persistant /app/data
- Container Running

---

## PHASE 8 ✅ — Intégration Home Assistant

- Onglet Energy HA : Session Energy ajouté comme Individual device
- Dashboard Lovelace : Status, Live Session, History, Connectivity
- Bouton Start/Stop conditionnel (câble branché requis)
- 7 automatisations : branché, débranché, charge démarrée, arrêtée, bridge offline, cloud offline, erreur EVSE
- HOME_ASSISTANT_DASHBOARD.yaml sauvegardé
- HOME_ASSISTANT_AUTOMATIONS.yaml sauvegardé

---

## Notes techniques

- Le X6 utilise le format OCPI (ocpiHomeStations), contrairement au X5 (legacyHomeStations)
- Auth PingIdentity : PKCE statique codé dans l'APK (inhabituel mais fonctionnel)
- Refresh token expire ~450 jours — re-auth rare
- La borne reporte au cloud toutes les 30 secondes pendant une charge
- Entity IDs HA basés sur noms français (premier démarrage) — ex: sensor.flo_home_x6_puissance
- Pull Policy TrueNAS : Always pull (redémarrer container pour update)
