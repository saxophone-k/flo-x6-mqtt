class FloAuthError(Exception):
    """Erreur d'authentification (credentials invalides, token expiré non renouvelable)."""
    pass

class FloNetworkError(Exception):
    """Erreur réseau (internet down, timeout, cloud Flo inaccessible)."""
    pass

class FloAPIError(Exception):
    """Erreur retournée par l'API Flo (HTTP 4xx/5xx inattendu)."""
    pass
