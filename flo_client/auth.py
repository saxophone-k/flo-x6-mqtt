"""
Authentification PingIdentity OAuth2 PKCE pour l'API Flo.

Flux complet découvert par reverse engineering de l'APK (Phase 2) et
interception réseau (Phase 3) :
  1. POST as/authorize  → obtenir un flowId PingIdentity
  2. POST flows/{id}    → vérifier username/password
  3. GET  as/resume     → obtenir le code d'autorisation
  4. POST as/token      → échanger le code contre access/refresh token
  5. POST as/token      → renouveler via refresh_token (expire ~450 jours)
"""

import json
import logging
import os
import time
from urllib.parse import urlparse, parse_qs

import requests

from .exceptions import FloAuthError, FloNetworkError

logger = logging.getLogger(__name__)

# --- Constantes extraites de l'APK (immuables) ---
_PING_BASE = "https://auth.pingone.ca"
_ENV_ID    = "6cedc65f-98e2-4651-bdb8-88ee4936c9ba"
_CLIENT_ID = "a52eedc6-7bcc-4d35-a57a-ef2685bd8101"
_SCOPE     = "eMobility:all"

# PKCE statique (codé en dur dans l'APK — inhabituel mais fonctionnel)
_CODE_CHALLENGE        = "Ir58yNWC3iBrKTmFce-hVSCKZrHXDnwHYADvwoSuZjk"
_CODE_CHALLENGE_METHOD = "S256"
_CODE_VERIFIER         = (
    "krVA8XsKmrVqo_rxbqWw1sDeXSdsf8W1G-x3D035zTnFbBcYjc5_Sd9yVhVFMd8v_"
    "M7nbpe0fbj0Ng0m9iZ3D0kUg8JjcNR0NZbQkrvhx9M-JVKW9nS00KZuVZ9zgfZP"
)

_TOKEN_FILE = os.path.join("data", "tokens.json")


def authenticate(username: str, password: str, timeout: int = 10) -> dict:
    """
    Authentifie l'utilisateur et retourne les tokens.

    Retourne un dict :
      { access_token, refresh_token, expires_at (timestamp Unix) }

    Lève FloAuthError si les credentials sont invalides.
    Lève FloNetworkError en cas de problème réseau.
    """
    session = requests.Session()
    base = f"{_PING_BASE}/{_ENV_ID}"

    try:
        # Étape 1 : démarrer le flow OAuth2 PKCE
        logger.debug("Auth étape 1 : POST as/authorize")
        resp = session.post(
            f"{base}/as/authorize",
            data={
                "client_id":             _CLIENT_ID,
                "response_type":         "code",
                "response_mode":         "pi.flow",
                "scope":                 _SCOPE,
                "code_challenge":        _CODE_CHALLENGE,
                "code_challenge_method": _CODE_CHALLENGE_METHOD,
            },
            headers={"Accept-Language": "fr-CA"},
            timeout=timeout,
            allow_redirects=False,
        )
        logger.debug("Authorize → %s : %s", resp.status_code, resp.text[:300])

        flow_id = _extract_flow_id(resp)
        if not flow_id:
            raise FloAuthError(f"Impossible d'obtenir un flowId. Réponse : {resp.text[:200]}")

        logger.debug("FlowId obtenu : %s", flow_id)

        # Étape 2 : vérifier username + password
        logger.debug("Auth étape 2 : POST flows/%s (check credentials)", flow_id)
        resp = session.post(
            f"{base}/flows/{flow_id}",
            json={"username": username, "password": password},
            headers={
                "Content-Type": "application/vnd.pingidentity.usernamePassword.check+json"
            },
            timeout=timeout,
        )
        logger.debug("CheckCredentials → %s : %s", resp.status_code, resp.text[:300])

        if resp.status_code in (400, 401, 403):
            raise FloAuthError("Credentials invalides (username ou password incorrect).")
        if resp.status_code >= 400:
            raise FloAuthError(f"Erreur auth étape 2 : HTTP {resp.status_code} — {resp.text[:200]}")

        # Étape 3 : résumer le flow pour obtenir le code d'autorisation
        logger.debug("Auth étape 3 : GET as/resume?flowId=%s", flow_id)
        resp = session.get(
            f"{base}/as/resume",
            params={"flowId": flow_id},
            timeout=timeout,
            allow_redirects=False,
        )
        logger.debug("Resume → %s : %s", resp.status_code, resp.text[:300])

        code = _extract_auth_code(resp)
        if not code:
            raise FloAuthError(f"Code d'autorisation introuvable. Réponse : {resp.text[:200]}")

        logger.debug("Code d'autorisation obtenu.")

        # Étape 4 : échanger le code contre des tokens
        return _exchange_code_for_tokens(session, base, code, timeout)

    except requests.Timeout:
        raise FloNetworkError("Timeout lors de l'authentification Flo.")
    except requests.ConnectionError as e:
        raise FloNetworkError(f"Erreur de connexion lors de l'authentification : {e}")


def refresh_access_token(refresh_token: str, timeout: int = 10) -> dict:
    """
    Renouvelle l'access token via le refresh token (expire ~450 jours).

    Retourne un dict : { access_token, refresh_token, expires_at }
    Lève FloAuthError si le refresh token est invalide ou expiré.
    """
    base = f"{_PING_BASE}/{_ENV_ID}"
    try:
        logger.debug("Rafraîchissement du token...")
        resp = requests.post(
            f"{base}/as/token",
            data={
                "client_id":     _CLIENT_ID,
                "grant_type":    "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=timeout,
        )
        if resp.status_code in (400, 401):
            raise FloAuthError("Refresh token invalide ou expiré — re-authentification requise.")
        resp.raise_for_status()

        data = resp.json()
        tokens = {
            "access_token":  data["access_token"],
            "refresh_token": data.get("refresh_token", refresh_token),
            "expires_at":    int(time.time()) + data.get("expires_in", 3600) - 60,
        }
        logger.info("Token rafraîchi avec succès.")
        return tokens

    except requests.Timeout:
        raise FloNetworkError("Timeout lors du refresh token.")
    except requests.ConnectionError as e:
        raise FloNetworkError(f"Erreur réseau lors du refresh token : {e}")


def load_tokens() -> dict | None:
    """Charge les tokens sauvegardés depuis data/tokens.json. Retourne None si absent."""
    if not os.path.exists(_TOKEN_FILE):
        return None
    try:
        with open(_TOKEN_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, KeyError):
        return None


def save_tokens(tokens: dict) -> None:
    """Sauvegarde les tokens dans data/tokens.json."""
    os.makedirs("data", exist_ok=True)
    with open(_TOKEN_FILE, "w") as f:
        json.dump(tokens, f, indent=2)
    logger.debug("Tokens sauvegardés.")


def get_valid_access_token(username: str, password: str, timeout: int = 10) -> str:
    """
    Retourne un access token valide.

    Logique :
      1. Charger les tokens sauvegardés
      2. Si access token encore valide → le retourner directement
      3. Si expiré mais refresh token disponible → rafraîchir
      4. Sinon → re-authentification complète avec username/password
    """
    tokens = load_tokens()

    if tokens:
        # Access token encore valide (avec 60s de marge)
        if tokens.get("expires_at", 0) > time.time():
            logger.debug("Token en cache encore valide.")
            return tokens["access_token"]

        # Tenter le refresh
        if tokens.get("refresh_token"):
            try:
                logger.info("Access token expiré — tentative de refresh...")
                tokens = refresh_access_token(tokens["refresh_token"], timeout)
                save_tokens(tokens)
                return tokens["access_token"]
            except FloAuthError:
                logger.warning("Refresh échoué — re-authentification complète.")

    # Authentification complète
    logger.info("Authentification complète avec username/password...")
    tokens = authenticate(username, password, timeout)
    save_tokens(tokens)
    return tokens["access_token"]


# --- Fonctions utilitaires privées ---

def _extract_flow_id(resp: requests.Response) -> str | None:
    """Extrait le flowId depuis la réponse de l'endpoint authorize."""
    # Tentative 1 : JSON (mode pi.flow retourne souvent du JSON)
    try:
        data = resp.json()
        # Chercher id, flowId ou _links dans la réponse
        if "id" in data:
            return data["id"]
        if "flowId" in data:
            return data["flowId"]
        # Parfois dans _links
        if "_links" in data and "self" in data["_links"]:
            href = data["_links"]["self"].get("href", "")
            parts = href.rstrip("/").split("/")
            if parts:
                return parts[-1]
    except (ValueError, KeyError):
        pass

    # Tentative 2 : Location header (redirect vers flows/{id})
    location = resp.headers.get("Location", "")
    if "/flows/" in location:
        return location.split("/flows/")[-1].split("?")[0]

    return None


def _extract_auth_code(resp: requests.Response) -> str | None:
    """Extrait le code d'autorisation depuis la réponse du resume."""
    # Tentative 1 : JSON (pi.flow retourne parfois le code dans le body)
    try:
        data = resp.json()
        if "code" in data:
            return data["code"]
        if "authorizeResponse" in data:
            return data["authorizeResponse"].get("code")
    except (ValueError, KeyError):
        pass

    # Tentative 2 : Location header (redirect vers URL scheme de l'app)
    location = resp.headers.get("Location", "")
    if location and "code=" in location:
        parsed = urlparse(location)
        params = parse_qs(parsed.query)
        codes = params.get("code", [])
        if codes:
            return codes[0]

    return None


def _exchange_code_for_tokens(
    session: requests.Session, base: str, code: str, timeout: int
) -> dict:
    """Échange un code d'autorisation contre des access/refresh tokens."""
    logger.debug("Auth étape 4 : POST as/token (échange code → tokens)")
    resp = session.post(
        f"{base}/as/token",
        data={
            "client_id":     _CLIENT_ID,
            "grant_type":    "authorization_code",
            "code":          code,
            "code_verifier": _CODE_VERIFIER,
        },
        timeout=timeout,
    )
    logger.debug("Token exchange → %s : %s", resp.status_code, resp.text[:200])

    if resp.status_code >= 400:
        raise FloAuthError(f"Échec échange code/token : HTTP {resp.status_code} — {resp.text[:200]}")

    data = resp.json()
    tokens = {
        "access_token":  data["access_token"],
        "refresh_token": data["refresh_token"],
        "expires_at":    int(time.time()) + data.get("expires_in", 3600) - 60,
    }
    logger.info("Authentification réussie. Token valide %ds.", data.get("expires_in", 3600))
    return tokens
