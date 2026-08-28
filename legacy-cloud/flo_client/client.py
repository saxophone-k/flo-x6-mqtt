"""
Client API Flo X6.

Endpoints utilisés (base : https://emobility.flo.ca) :
  GET  /v3.1/homestation                                    → état de la borne
  GET  /v3.1/user/sessions                                  → session active
  POST /v3.1/homestation/chargingstation/{uid}/session/start → démarrer la charge
  POST /v3.1/homestation/chargingstation/{uid}/session/stop  → arrêter la charge
  POST /v3.0/stations/{uid}/fast-status-update               → forcer refresh statut
"""

import logging
import requests

from .exceptions import FloAuthError, FloNetworkError, FloAPIError

logger = logging.getLogger(__name__)

_API_BASE = "https://emobility.flo.ca"


class FloX6Client:
    """Client pour l'API REST de la borne Flo X6."""

    def __init__(self, access_token: str, timeout: int = 10):
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        })

    def update_token(self, access_token: str) -> None:
        """Met à jour le token d'accès (après un refresh)."""
        self._session.headers["Authorization"] = f"Bearer {access_token}"

    # --- Lecture ---

    def get_station(self) -> dict:
        """
        Retourne l'état complet de la borne (OcpiStation).

        Structure retournée :
          chargingStationUid, physicalReference, connectionStatus,
          evse.status, evse.connectors[].maxAmperage/maxVoltage,
          firmwareVersion, model, homeModelType, lastUpdated,
          stationPreferences.nickname
        """
        data = self._get("/v3.1/homestation")

        # Le X6 utilise le format OCPI (pas legacy comme le X5)
        ocpi_stations = data.get("ocpiHomeStations", [])
        if not ocpi_stations:
            raise FloAPIError("Aucune borne OCPI trouvée pour ce compte.")

        return ocpi_stations[0]

    def get_session(self) -> dict | None:
        """
        Retourne la session de charge active, ou None si aucune session.

        Structure retournée :
          id, sessionState, amperage, amperageOffer, voltage,
          energyTransferredWh, durationMs, startDate, stateOfCharge,
          cost.estimatedCost, cost.currency, station.id
        """
        sessions = self._get("/v3.1/user/sessions")
        if not sessions:
            return None
        # Ne retourner que les sessions actives (pas Completed, Stopped, etc.)
        active = [s for s in sessions if s.get("sessionState") == "Charging"]
        return active[0] if active else None

    # --- Commandes ---

    def start_charge(self, station_uid: str, evse_id: str = "1", connector_id: str = None) -> bool:
        """
        Démarre une session de charge.

        station_uid  : chargingStationUid de la borne (ex: YOUR-STATION-UID)
        evse_id      : identifiant EVSE, toujours "1" pour le X6
        connector_id : identifiant connecteur (optionnel selon l'APK)
        Retourne True si la commande a été acceptée.
        """
        endpoint = f"/v3.1/homestation/chargingstation/{station_uid}/session/start"
        body = {"evseId": evse_id}
        if connector_id is not None:
            body["connectorId"] = connector_id
        try:
            self._post(endpoint, body=body)
            logger.info("Commande start_charge envoyée (EVSE %s).", evse_id)
            return True
        except FloAPIError as e:
            logger.error("Erreur start_charge : %s", e)
            return False

    def stop_charge(self, station_uid: str) -> bool:
        """
        Arrête la session de charge en cours.

        station_uid : chargingStationUid de la borne
        Retourne True si la commande a été acceptée.
        """
        endpoint = f"/v3.1/homestation/chargingstation/{station_uid}/session/stop"
        try:
            self._post(endpoint, body={})
            logger.info("Commande stop_charge envoyée.")
            return True
        except FloAPIError as e:
            logger.error("Erreur stop_charge : %s", e)
            return False

    def get_schedule(self, station_uid: str) -> dict:
        """Retourne le schedule actuel de la borne."""
        return self._get(f"/v3.1/homestation/{station_uid}/schedule")

    def set_schedule_enabled(self, station_uid: str, enabled: bool) -> bool:
        """
        Active ou désactive le schedule (toggle isEnabled).

        Pré-requis : l'utilisateur doit avoir créé dans l'app Flo un schedule
        24h/24 365 jours avec powerOutput=0 pour que ce toggle bloque la charge.

        enabled=True  → schedule actif → charge bloquée (si configuré en 0W)
        enabled=False → schedule inactif → charge normale
        """
        try:
            schedule = self.get_schedule(station_uid)
            schedule["isEnabled"] = enabled
            self._put(f"/v3.1/homestation/{station_uid}/schedule", body=schedule)
            logger.info("Schedule %s.", "activé (charge bloquée)" if enabled else "désactivé (charge normale)")
            return True
        except (FloNetworkError, FloAPIError) as e:
            logger.error("Erreur set_schedule_enabled : %s", e)
            return False

    def fast_status_update(self, station_uid: str) -> bool:
        """
        Force la borne à remonter immédiatement son statut au cloud.
        Utile après un start/stop pour avoir l'état frais sans attendre.

        station_uid : chargingStationUid de la borne
        """
        endpoint = f"/v3.0/stations/{station_uid}/fast-status-update"
        try:
            self._post(endpoint, body={})
            logger.debug("fast-status-update envoyé.")
            return True
        except FloAPIError as e:
            logger.warning("fast-status-update échoué : %s", e)
            return False

    # --- Méthodes HTTP privées ---

    def _get(self, path: str) -> any:
        """Effectue un GET et retourne le JSON décodé."""
        url = f"{_API_BASE}{path}"
        try:
            resp = self._session.get(url, timeout=self._timeout)
            self._handle_response(resp, url)
            return resp.json()
        except requests.Timeout:
            raise FloNetworkError(f"Timeout sur GET {path}")
        except requests.ConnectionError as e:
            raise FloNetworkError(f"Erreur connexion sur GET {path} : {e}")

    def _put(self, path: str, body: dict) -> any:
        """Effectue un PUT avec un body JSON et retourne le JSON décodé (si présent)."""
        url = f"{_API_BASE}{path}"
        try:
            resp = self._session.put(url, json=body, timeout=self._timeout)
            self._handle_response(resp, url)
            if resp.content:
                return resp.json()
            return None
        except requests.Timeout:
            raise FloNetworkError(f"Timeout sur PUT {path}")
        except requests.ConnectionError as e:
            raise FloNetworkError(f"Erreur connexion sur PUT {path} : {e}")

    def _post(self, path: str, body: dict) -> any:
        """Effectue un POST avec un body JSON et retourne le JSON décodé (si présent)."""
        url = f"{_API_BASE}{path}"
        try:
            resp = self._session.post(url, json=body, timeout=self._timeout)
            self._handle_response(resp, url)
            if resp.content:
                return resp.json()
            return None
        except requests.Timeout:
            raise FloNetworkError(f"Timeout sur POST {path}")
        except requests.ConnectionError as e:
            raise FloNetworkError(f"Erreur connexion sur POST {path} : {e}")

    def _handle_response(self, resp: requests.Response, url: str) -> None:
        """Vérifie le code HTTP et lève l'exception appropriée."""
        if resp.status_code in (401, 403):
            raise FloAuthError(f"Token invalide ou expiré (HTTP {resp.status_code}) sur {url}")
        if resp.status_code >= 400:
            raise FloAPIError(
                f"Erreur API HTTP {resp.status_code} sur {url} : {resp.text[:200]}"
            )
