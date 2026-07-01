"""Seguridad del dashboard: verificación de contraseña y sesiones firmadas.

Ver CLAUDE.md §6:
- Comparación segura de contraseña (tiempo constante; soporta hash bcrypt).
- Cookie de sesión firmada con SESSION_SECRET (la marca HttpOnly/SameSite/Secure y la
  expiración las pone la capa web al emitir la cookie).
"""

from __future__ import annotations

import hmac

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

# Espacio de nombres de la firma (evita reusar el secreto para otros propósitos).
_SESSION_SALT = "brujula.session.v1"
_SESSION_VALUE = "ok"


def verify_password(plain: str, expected: str) -> bool:
    """Compara la contraseña ingresada contra la configurada.

    Si `expected` parece un hash bcrypt (`$2...`) se verifica con passlib; en caso
    contrario se hace una comparación en tiempo constante con el valor en claro del `.env`.
    """
    if not expected:
        return False
    if expected.startswith("$2"):
        try:
            from passlib.hash import bcrypt

            return bool(bcrypt.verify(plain, expected))
        except Exception:  # noqa: BLE001 - hash inválido → acceso denegado
            return False
    return hmac.compare_digest(plain.encode("utf-8"), expected.encode("utf-8"))


def _serializer(secret: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret, salt=_SESSION_SALT)


def issue_session(secret: str) -> str:
    """Genera un token de sesión firmado (con marca de tiempo)."""
    return _serializer(secret).dumps(_SESSION_VALUE)


def validate_session(token: str, secret: str, max_age: int = 28800) -> bool:
    """Valida un token de sesión: firma correcta y no expirado (`max_age` segundos)."""
    if not token or not secret:
        return False
    try:
        value = _serializer(secret).loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return False
    return bool(value == _SESSION_VALUE)
