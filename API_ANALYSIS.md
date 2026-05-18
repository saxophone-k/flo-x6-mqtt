# API_ANALYSIS.md — Analyse statique de l'APK Flo
Version APK analysée : 3.4.20 (com.addenergie.reseauver)
Date d'analyse : 2026-05-15
Source : jadx 1.5.0 + apktool 2.7.0

---

## 1. URLs de base

### Environnement PRODUCTION — Canada (notre cible)
| Paramètre | Valeur |
|-----------|--------|
| API Base URL | `https://emobility.flo.ca/` |
| Auth URL (PingIdentity) | `https://auth.pingone.ca` |
| API PingIdentity | `https://api.pingone.ca/v1` |
| Environment ID | `6cedc65f-98e2-4651-bdb8-88ee4936c9ba` |
| Application ID | `a52eedc6-7bcc-4d35-a57a-ef2685bd8101` |

### Autres environnements trouvés (ne pas utiliser)
| Environnement | URL |
|--------------|-----|
| Dev Canada | `https://emobility-floca-dev1.addtest.site/` |
| QA Canada | `https://emobility-floca-qa.addtest.site/` |
| Prod USA | `https://emobility.servicesflo.com/` |

---

## 2. Mécanisme d'authentification

L'app utilise **PingIdentity OAuth2 avec PKCE** (Proof Key for Code Exchange).

### Flux d'authentification
```
1. POST https://auth.pingone.ca/as/authorize
   → Démarre le flow OAuth2 (retourne un flowId)

2. POST https://auth.pingone.ca/flows/{flowId}
   Header: Content-Type: application/vnd.pingidentity.usernamePassword.check+json
   Body: { "username": "...", "password": "..." }
   → Vérifie les credentials, retourne un code d'autorisation

3. GET https://auth.pingone.ca/as/resume?flowId={flowId}
   → Obtient le code d'autorisation final

4. POST https://auth.pingone.ca/as/token
   Body (form-encoded):
     client_id=a52eedc6-7bcc-4d35-a57a-ef2685bd8101
     grant_type=authorization_code
     code={code_retourné}
     code_verifier={PKCE_verifier}
   → Retourne { access_token, refresh_token }
```

### Constantes PKCE (statiques dans l'app — utilisées pour toutes les sessions)
```
PKCE_CODE_CHALLENGE        = Ir58yNWC3iBrKTmFce-hVSCKZrHXDnwHYADvwoSuZjk
PKCE_CODE_CHALLENGE_METHOD = S256
PKCE_CODE_VERIFIER         = krVA8XsKmrVqo_rxbqWw1sDeXSdsf8W1G-x3D035zTnFbBcYjc5_Sd9yVhVFMd8v_M7nbpe0fbj0Ng0m9iZ3D0kUg8JjcNR0NZbQkrvhx9M-JVKW9nS00KZuVZ9zgfZP
```
> **Note :** Ces constantes sont codées en dur dans l'APK. Cela signifie que l'app utilise
> un client PKCE statique — inhabituel mais fonctionnel. À confirmer via interception réseau.

### Scopes OAuth2
```
eMobility:all                                          ← scope API Flo
openid profile p1:read:user p1:update:user ...         ← scope PingIdentity
```

### Utilisation du token
```
Header de chaque requête API :
  Authorization: Bearer {access_token}
```

### Refresh du token
```
POST https://auth.pingone.ca/as/token
Body (form-encoded):
  client_id=a52eedc6-7bcc-4d35-a57a-ef2685bd8101
  grant_type=refresh_token
  refresh_token={refresh_token}
```

### Stockage des tokens (dans l'app Android)
```
SharedPreferences keys :
  addEnergieAccessToken              ← JWT access token
  addEnergieRefreshToken             ← refresh token
  addEnergieLastRefreshTokenChangeDate ← timestamp (long, ms)
```

### Détection d'expiration
L'app décode le JWT avec `com.auth0.android.jwt.JWT` et vérifie `expiresAt`.
Si expiré ou vide → refresh automatique.

---

## 3. Endpoints API — Borne domestique (v3.1)

Base URL : `https://emobility.flo.ca/`

### Lecture de l'état de la borne
```
GET v3.1/homestation
→ HomeStation { ocpiHomeStations[], legacyHomeStations[] }
  ocpiHomeStations est le format moderne utilisé par X6
```

```
GET v3.1/homestation/{chargingStationUid}/address
→ Address
```

```
GET v3.1/homestation/{chargingStationId}/schedule
→ HomeStationSchedule
```

### Démarrage / Arrêt de charge
```
POST v3.1/homestation/chargingstation/{chargingStationID}/session/start
Body: StartOcpiHomeStationSessionBody
→ 200 OK (vide)
```

```
POST v3.1/homestation/chargingstation/{chargingStationID}/session/stop
→ 200 OK (vide)
```

### Configuration de la borne
```
PUT v3.1/homestation/{chargingStationUid}/configuration
Body: Configurations
→ Configurations

PUT v3.1/homestation/{chargingStationUid}/preferences
Body: StationPreferences { nickname, configurations }
→ StationPreferences

PUT v3.1/homestation/{chargingStationId}/schedule
Body: HomeStationSchedule
→ HomeStationSchedule
```

### Association (appairage — lecture seule pour nous)
```
POST v3.1/homestation/association       ← apparier une nouvelle borne
DELETE v3.1/homestation/{uid}/association ← dissocier
POST v3.1/homestation/X5/association/{code} ← flow legacy X5
```

---

## 4. Endpoints API — Sessions en cours (v3.1)

```
GET v3.1/user/sessions
→ BackendSession[] (liste des sessions actives en temps réel)
```

---

## 5. Endpoints API — Autres (v3.0)

### Profil utilisateur
```
GET  v3.0/user/profile   → UserProfile
PUT  v3.0/user/profile   → UserProfile (mise à jour)
DEL  v3.0/user/profile   → suppression
GET  v3.0/user/accounts  → UserAccount (portefeuille)
GET  v3.0/user/addresses → UserAddresses
```

### Historique des transactions
```
POST v3.1/user/transactions/search → LinkedTransactions (filtré)
GET  v3.0/user/transactions/{id}/home-charging → HomeChargingTransaction
GET  v3.0/user/transactions/{id}/network-charging
GET  v3.0/user/transactions/{id}/add-funds
```

### Notifications
```
GET  v3.0/user/notifications  → Notifications
POST v3.0/user/notifications  → mise à jour
```

### Carte de recharge réseau
```
GET  v3.0/map/networks       → Network[]
POST v3.0/map/markers/search → Markers
POST v3.0/parks/nearest      → Markers
```

---

## 6. Modèles de données détaillés

### OcpiStation (état complet de la borne X6)
```json
{
  "chargingStationUid": "string",        ← ID unique de la borne
  "physicalReference": "string",          ← étiquette physique
  "connectionStatus": "string",           ← connexion réseau
  "vendor": "string",                     ← fabricant
  "model": "string",                      ← modèle (X6)
  "homeModelType": "X6",                  ← enum: X3|X5|X6|X8|Unknown
  "firmwareVersion": "string",            ← version firmware
  "lastUpdated": "string",                ← timestamp ISO 8601
  "associationCode": "string",
  "physicalReference": "string",
  "stationPreferences": {
    "nickname": "string",                 ← surnom configuré par l'utilisateur
    "configurations": { ... }            ← voir Configurations
  },
  "evse": {
    "id": "string",
    "status": "Available|Blocked|Charging|Inoperative|OutOfOrder|PluggedIn|Reserved|Unknown",
    "capabilities": [],
    "connectors": [{
      "type": "string",                  ← type de connecteur (J1772, etc.)
      "maxVoltage": 240,                 ← tension maximale (V)
      "maxAmperage": 48,                 ← ampérage maximal (A)
      "lastUpdated": "string"
    }],
    "lastUpdated": "string"
  },
  "schedule": { ... }                    ← planification de charge
}
```

### BackendSession (session de charge en temps réel)
```json
{
  "id": "string",                         ← ID de session
  "sessionState": "string",              ← état: Charging, Completed, etc.
  "sessionType": "Home|Public",          ← type de session
  "startDate": "string",                 ← heure de début (ISO 8601)
  "durationMs": 3600000,                 ← durée en millisecondes
  "energyTransferredWh": 7500.0,         ← énergie transférée en Wh
  "amperage": 32.0,                      ← ampérage actuel (A)
  "amperageOffer": 32.0,                 ← ampérage offert (A)
  "voltage": 240.0,                      ← tension (V)
  "stateOfCharge": 80.0,                 ← % batterie véhicule (nullable)
  "lastRefreshMs": 1234567890,           ← timestamp dernier rafraîchissement
  "station": {
    "id": "string",
    "name": "string",
    "parkName": "string",
    "model": "string"
  },
  "cost": {
    "estimatedCost": 2.50,              ← coût estimé
    "currency": "CAD"
  },
  "authorizationStatus": { ... },
  "restrictions": { ... },
  "sessionNetwork": { ... }
}
```

### Configurations (réglages de la borne)
Contient `restrictedAccess` (Boolean) et `version` — à confirmer par interception réseau.

### StationPreferences
```json
{
  "nickname": "string",     ← nom personnalisé de la borne
  "configurations": { ... }
}
```

---

## 7. OcpiStatus — Valeurs possibles
| Valeur | Signification |
|--------|---------------|
| Available | Borne disponible, câble débranché |
| PluggedIn | Câble branché, pas en charge |
| Charging | Charge active |
| Blocked | Bloquée |
| Inoperative | Hors service temporaire |
| OutOfOrder | En panne |
| Planned | Prévue (pas encore opérationnelle) |
| Reserved | Réservée |
| Removed | Désinstallée |
| Unknown | État inconnu |

---

## 8. Modèles compatibles
L'app supporte : X3, X5, **X6**, X8
Le X6 utilise le format OCPI (ocpiHomeStations) contrairement au X5 (legacyHomeStations).

---

## 9. Points à confirmer par interception réseau (Phase 3)
- [ ] Format exact du body `StartOcpiHomeStationSessionBody` (champs requis)
- [ ] Valeurs possibles de `sessionState` (ex: "Charging", "Completed", "Idle"?)
- [ ] Valeurs possibles de `connectionStatus`
- [ ] Structure exacte de `Configurations` (champs ampérage max, etc.)
- [ ] Headers de réponse (rate limiting, cache-control)
- [ ] Comportement exact du token expiré (401 ou 403 ?)
- [ ] Est-ce que le PKCE est vraiment statique ou généré à chaque session ?
- [ ] Structure complète de `HomeStationSchedule`
- [ ] Champs de `StartOcpiHomeStationSessionBody`
