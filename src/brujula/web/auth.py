"""Login del dashboard: cookie de sesión firmada, rate-limit y dependencias de acceso.

Ver CLAUDE.md §6. La firma/validación del token vive en core.security; aquí se decide
la política de la cookie (HttpOnly, SameSite, Secure en prod) y el rate-limit de /login.
"""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import HTTPException, Request, Response, status

from brujula.config.settings import Settings, get_settings
from brujula.core.security import issue_session, validate_session

COOKIE_NAME = "brujula_session"
SESSION_MAX_AGE = 28800  # 8 horas

# Rate-limit en memoria (single-user): intentos fallidos por IP dentro de una ventana.
_MAX_ATTEMPTS = 5
_WINDOW_SECS = 300
_attempts: dict[str, list[float]] = defaultdict(list)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def login_allowed(request: Request) -> bool:
    """True si la IP aún tiene intentos disponibles en la ventana actual."""
    ip = _client_ip(request)
    now = time.time()
    recientes = [t for t in _attempts[ip] if now - t < _WINDOW_SECS]
    _attempts[ip] = recientes
    return len(recientes) < _MAX_ATTEMPTS


def register_failed_attempt(request: Request) -> None:
    _attempts[_client_ip(request)].append(time.time())


def reset_attempts(request: Request) -> None:
    _attempts.pop(_client_ip(request), None)


def is_authenticated(request: Request, settings: Settings | None = None) -> bool:
    """True si la cookie de sesión es válida y no ha expirado."""
    settings = settings or get_settings()
    token = request.cookies.get(COOKIE_NAME, "")
    return validate_session(token, settings.session_secret, SESSION_MAX_AGE)


def set_session_cookie(response: Response, settings: Settings | None = None) -> None:
    """Emite la cookie de sesión firmada con las marcas de seguridad correctas."""
    settings = settings or get_settings()
    response.set_cookie(
        key=COOKIE_NAME,
        value=issue_session(settings.session_secret),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="strict",
        secure=settings.is_production,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


async def require_api_session(request: Request) -> None:
    """Dependencia para rutas /api/*: 401 si no hay sesión válida."""
    if not is_authenticated(request):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")
