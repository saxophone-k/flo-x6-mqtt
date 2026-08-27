# ENTITIES_DISCOVERED.md — Entités Home Assistant
Version finale : Phase 2 (APK) + Phase 3 (interception réseau) + Phase 4 (test réel API)
Dernière mise à jour : 2026-05-17

---

## DEVICE HOME ASSISTANT

Un seul device "Flo X6" regroupant toutes les entités :
- **Nom** : Flo Home X6 (ou le surnom configuré dans l'app)
- **Identifiant unique** : chargingStationUid (600a3f7d-...)
- **Fabricant** : flo
- **Modèle** : FLO Home X6
- **Version firmware** : 3.0.0

---

## ENTITÉS — ÉTAT DE LA BORNE

Source : `GET /v3.1/homestation`

| Entité HA | Type | Champ API | Unité | Valeurs possibles | Notes |
|-----------|------|-----------|-------|-------------------|-------|
| Borne connectée | binary_sensor | `connectionStatus == "Online"` | — | true/false | device_class: connectivity |
| Câble branché | binary_sensor | `evse.status ∈ {PluggedIn,Charging,Reserved}` | — | true/false | device_class: plug |
| En charge | binary_sensor | `evse.status == "Charging"` | — | true/false | device_class: battery_charging |
| Borne en erreur | binary_sensor | `evse.status ∈ {Inoperative,OutOfOrder}` | — | true/false | device_class: problem |
| Statut EVSE | sensor | `evse.status` | — | Available, PluggedIn, Charging, Blocked, Inoperative, OutOfOrder, Planned, Reserved, Unknown | État principal |
| Ampérage max borne | sensor | `evse.connectors[0].maxAmperage` | A | 48 | capacité physique |
| Puissance max | sensor | `maxOutput` | A | 50 | capacité nominale |
| Modèle | sensor | `model` | — | FLO Home X6 | diagnostic |
| Firmware | sensor | `firmwareVersion` | — | 3.0.0 | diagnostic |
| Surnom | sensor | `stationPreferences.nickname` | — | string | configuré par l'utilisateur |
| Fuseau horaire | sensor | `stationPreferences.configurations.timezone.value` | — | America/Toronto | diagnostic |
| Dernière mise à jour borne | sensor | `lastUpdated` | — | ISO 8601 | device_class: timestamp |

---

## ENTITÉS — SESSION DE CHARGE EN TEMPS RÉEL

Source : `GET /v3.1/user/sessions`

| Entité HA | Type | Champ API | Unité | Notes |
|-----------|------|-----------|-------|-------|
| Session active | binary_sensor | liste sessions non vide | — | true si charge en cours |
| État session | sensor | `sessionState` | — | Charging, Completed, ... |
| Ampérage actuel | sensor | `amperage` | A | device_class: current |
| Ampérage offert | sensor | `amperageOffer` | A | max disponible |
| Tension | sensor | `voltage` | V | device_class: voltage |
| Puissance actuelle | sensor | `amperage × voltage` (calculé) | W | device_class: power |
| Énergie transférée | sensor | `energyTransferredWh ÷ 1000` | kWh | device_class: energy — clé pour onglet Energy HA |
| Durée session | sensor | `durationMs ÷ 60000` | min | |
| Heure de début | sensor | `startDate` | — | device_class: timestamp |
| Coût estimé | sensor | `cost.estimatedCost` | $ | |
| Devise | sensor | `cost.currency` | — | CAD |
| % Batterie véhicule | sensor | `stateOfCharge` | % | nullable — absent si voiture ne transmet pas |
| Mode restriction | sensor | `restrictions.activeRestriction` | — | NoRestriction, ... |
| Partage de puissance | sensor | `restrictions.powerSharingMode` | — | None, ... |

---

## ENTITÉS — PLANIFICATION

Source : `schedule` dans `GET /v3.1/homestation`

| Entité HA | Type | Champ API | Notes |
|-----------|------|-----------|-------|
| Planification activée | binary_sensor | `schedule.isEnabled` | true/false |
| Mode planification | sensor | `schedule.kind` | "manual" ou "scheduled" |

---

## ENTITÉS — CONFIGURATION

Source : `stationPreferences.configurations` dans `GET /v3.1/homestation`

| Entité HA | Type | Champ API | Notes |
|-----------|------|-----------|-------|
| Profil charge récurrent | binary_sensor | `configurations.recurringChargingProfile.value` | true/false |
| Accès restreint | binary_sensor | `configurations.restrictedAccess.value` | true/false |

---

## ENTITÉS — DEMAND RESPONSE

Source : `demandResponse` dans `GET /v3.1/homestation`

| Entité HA | Type | Notes |
|-----------|------|-------|
| Demand response actif | binary_sensor | `demandResponse.upcoming` non vide |

---

## COMMANDES

| Entité HA | Type | Endpoint | Body | Notes |
|-----------|------|----------|------|-------|
| Démarrer la charge | button / switch | POST /v3.1/homestation/chargingstation/{uid}/session/start | `{"evseId":"1"}` | |
| Arrêter la charge | button / switch | POST /v3.1/homestation/chargingstation/{uid}/session/stop | `{}` | |

---

## ENTITÉS — DIAGNOSTIC DU BRIDGE

Source : état interne du daemon Python

| Entité HA | Type | Notes |
|-----------|------|-------|
| Bridge en ligne | binary_sensor | device_class: connectivity |
| Internet disponible | binary_sensor | ping 8.8.8.8 |
| Cloud Flo disponible | binary_sensor | HEAD emobility.flo.ca |
| Dernière MAJ réussie | sensor | device_class: timestamp |
| Cause dernière erreur | sensor | "Internet down", "Timeout", "Auth expired", ... |
| Erreurs consécutives | sensor | compteur, reset à 0 quand OK |

---

## INTÉGRATION ONGLET ENERGY HOME ASSISTANT

Le sensor `energyTransferredWh` (device_class: energy, state_class: total_increasing)
permet d'ajouter la borne dans l'onglet Energy de HA comme consommateur individuel.
HA calculera automatiquement les statistiques : kWh/jour, kWh/mois, coût si tarif configuré.

> ⚠️ Note : `energyTransferredWh` repart à 0 à chaque nouvelle session.
> Le daemon devra publier `state_class: total_increasing` et gérer la remise à zéro
> pour que l'onglet Energy cumule correctement sur la durée.
