# PROGRESS — flo-x6-mqtt

Projet : Bridge Flo X6 → MQTT → Home Assistant  
Démarré : 2026-05-15

---

## PHASE 1 — Setup environnement & téléchargement APK ✅ TERMINÉE

### Outils installés
- [x] python3 3.12.3
- [x] pip3 24.0
- [x] git 2.43.0
- [x] java OpenJDK 21
- [x] apktool 2.7.0
- [x] jadx 1.5.0
- [x] mitmproxy (préinstallé)
- [x] docker 29.1.3
- [x] docker compose 2.40.3

### Structure du projet créée
- [x] ~/flo-x6-mqtt/apk/
- [x] ~/flo-x6-mqtt/decompiled/
- [x] ~/flo-x6-mqtt/flo_client/
- [x] ~/flo-x6-mqtt/data/
- [x] ~/flo-x6-mqtt/.github/workflows/

### APK
- [x] APK téléchargé : com.addenergie.reseauver v3.4.20 (52 Mo)
- [x] APK patché avec apk-mitm (SSL pinning désactivé) : 53 Mo

---

## PHASE 2 — Décompilation & analyse statique ✅ TERMINÉE

### Outils de décompilation
- [x] jadx → 24 646 fichiers Java décompilés
- [x] apktool → ressources + smali

### Découvertes clés
- [x] API Base URL production Canada : https://emobility.flo.ca/
- [x] Auth : PingIdentity OAuth2 PKCE (auth.pingone.ca)
- [x] Environment ID : 6cedc65f-98e2-4651-bdb8-88ee4936c9ba
- [x] Application ID : a52eedc6-7bcc-4d35-a57a-ef2685bd8101
- [x] Endpoints station : GET/PUT v3.1/homestation + start/stop session
- [x] Modèle de données session : ampérage, tension, Wh, coût, état
- [x] Modèle de données borne : OcpiStation (X6 = format OCPI)
- [x] États EVSE : Available, PluggedIn, Charging, Inoperative, OutOfOrder, etc.

### Documents produits
- [x] API_ANALYSIS.md
- [x] ENTITIES_DISCOVERED.md (v1 — basée sur analyse statique)

---

## PHASE 3 — Interception trafic réseau ✅ TERMINÉE (laptop Windows)

### Méthode utilisée
- APK patché avec apk-mitm (SSL pinning désactivé)
- Émulateur Android Pixel 4 (Android APIs) sur Windows (8-16 Go RAM)
- mitmproxy/mitmweb sur Windows, proxy 10.0.2.2:8080
- Note : iPhone refusé (SSL pinning iOS), Linux Mint insuffisant en RAM

### Données borne confirmées
- Station UID : 600a3f7d-30ba-4d67-bd4a-8d72e6286666
- Station ID  : ef8d78af-90ec-47cd-8382-ad2b03429a1d
- EVSE ID     : 1
- Référence   : H5301CJ
- Modèle      : FLO Home X6, firmware 3.0.0, 48A max

### Authentification confirmée
- POST https://auth.pingone.ca/6cedc65f-98e2-4651-bdb8-88ee4936c9ba/as/token
- Client ID : a52eedc6-7bcc-4d35-a57a-ef2685bd8101
- Access token : expire 3600s (1h)
- Refresh token : expire ~450 jours
- 2 scopes distincts : eMobility:all (API Flo) + p1:update:user (PingOne)

### Endpoints confirmés
- GET  /v3.1/homestation → statut borne
- GET  /v3.1/user/sessions → session temps réel
- POST /v3.1/homestation/chargingstation/{uid}/session/start → body: {"evseId":"1"}
- POST /v3.1/homestation/chargingstation/{uid}/session/stop → body vide
- POST /v3.0/stations/{uid}/fast-status-update → body vide (forcer refresh)

---

## PHASE 5 — Daemon MQTT + Home Assistant Discovery ✅ TERMINÉE

### Fichier principal
- [x] main.py — boucle de polling adaptative (30s/60s/120s)
- [x] MQTT Discovery — 24 entités (sensors, binary_sensors, switch, diagnostic)
- [x] LWT configuré — HA marque offline si daemon crashe
- [x] Availability online/offline selon état réel
- [x] Reconnexion MQTT automatique avec republication complète
- [x] Retry infini au démarrage si broker absent
- [x] Guard commandes start/stop (délais mesurés)
- [x] Noms entités en anglais
- [x] Double Discovery au démarrage corrigé (flag first_connect)
- [x] Client ID MQTT unique basé sur UID borne

## PHASE 5.5 — Tests d'intégration ✅ TERMINÉE

- [x] B1  — Internet down → unavailable après ~3 min, recovery auto
- [x] B2  — Cloud Flo bloqué → unavailable après ~3 min, recovery auto
- [x] B3  — Broker MQTT tombe → reconnexion et recovery en ~5s
- [x] B4  — Broker éteint au démarrage → retry progressif 5→30s
- [x] B5  — Reconnexion après panne → validé avec B2
- [x] B7  — Câble débranché → EVSE Available après ~30s (cycle borne)
- [x] B10 — kill -9 → LWT instantané dans HA
- [x] A1-A13 — Tests automatisés : 12/12 PASS

## PHASE 4 — Client Python Flo X6 ✅ TERMINÉE

- [x] flo_client/exceptions.py — FloAuthError, FloNetworkError, FloAPIError
- [x] flo_client/auth.py — OAuth2 PKCE PingIdentity, refresh automatique, cache tokens
- [x] flo_client/client.py — get_station(), get_session(), start_charge(), stop_charge(), fast_status_update()
- [x] flo_client/connectivity.py — check_internet(), check_flo_api()
- [x] debug.py — affichage état brut complet
- [x] requirements.txt
- [x] Test avec vrais credentials → succès complet
- [x] ENTITIES_DISCOVERED.md mis à jour avec données réelles API

## PHASE 5 — Daemon MQTT + Home Assistant Discovery ⏳ À FAIRE

## PHASE 5.5 — Tests B (intégration complète) ⏳ À FAIRE AVANT GITHUB
> Ces tests nécessitent que main.py tourne et que HA soit intégré (après Phase 5).
> Obligatoires avant de pousser sur GitHub.

### Tests B — nécessitent intervention manuelle
- [ ] B1  — Couper le Wi-Fi de Linux Mint → vérifier que HA grise les entités, logs clairs
- [ ] B2  — Bloquer cloud Flo (iptables) → vérifier "offline" dans HA, retry automatique
- [ ] B3  — Arrêter broker MQTT pendant que daemon tourne → vérifier reconnexion automatique
- [ ] B4  — Démarrer daemon avec broker MQTT éteint → vérifier retry au démarrage
- [ ] B5  — Rebrancher internet après B1/B2 → vérifier retour "online" et republication état
- [ ] B6  — Borne perd sa connexion Wi-Fi → vérifier connectionStatus=Offline détecté
- [ ] B7  — Débrancher câble pendant charge → vérifier session disparaît, EVSE=Available
- [ ] B8  — Ouvrir app Flo iPhone après 1h de daemon → vérifier toujours connecté
- [ ] B9  — docker restart → vérifier tokens persistés, reprise sans re-auth
- [ ] B10 — kill -9 le daemon → vérifier LWT publie "offline" dans HA automatiquement

## PHASE 6 — Packaging Docker & GitHub ⏳ À FAIRE

## PHASE 7 — Custom App TrueNAS SCALE ⏳ À FAIRE

## PHASE 8 — Intégration Home Assistant ⏳ À FAIRE

---

## Notes & décisions
- Linux Mint 22 (base Ubuntu 24.04 noble)
- Erreurs dpkg linux-headers préexistantes sur le système, sans impact sur le projet
- Capture réseau : SSL pinning iOS contourné via APK patché + émulateur Android Windows
- Le X6 utilise le format OCPI (ocpiHomeStations), contrairement au X5 (legacyHomeStations)
- Body start session = {"evseId":"1"} (découvert Phase 3)
