"""
Vérification de la connectivité réseau (internet + cloud Flo).
Utilisé par le daemon avant chaque cycle de polling.
"""

import logging
import socket
import requests

logger = logging.getLogger(__name__)

_FLO_HEALTH_URL = "https://emobility.flo.ca"
_PING_HOST = "8.8.8.8"
_PING_PORT = 53
_PING_TIMEOUT = 3


def check_internet() -> bool:
    """
    Vérifie si internet est disponible en tentant une connexion TCP
    vers le DNS de Google (8.8.8.8:53).
    """
    try:
        socket.setdefaulttimeout(_PING_TIMEOUT)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(
            (_PING_HOST, _PING_PORT)
        )
        return True
    except (socket.error, OSError):
        logger.warning("Internet non disponible (ping 8.8.8.8 échoué).")
        return False


def check_flo_api(timeout: int = 5) -> bool:
    """
    Vérifie si le cloud Flo est accessible en faisant une requête HEAD
    vers l'URL de base de l'API.
    """
    try:
        resp = requests.head(_FLO_HEALTH_URL, timeout=timeout)
        # N'importe quelle réponse HTTP signifie que le serveur répond
        return True
    except (requests.ConnectionError, requests.Timeout):
        logger.warning("Cloud Flo non disponible (%s inaccessible).", _FLO_HEALTH_URL)
        return False
