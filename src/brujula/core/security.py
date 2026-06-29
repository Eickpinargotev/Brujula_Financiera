"""Seguridad del dashboard: verificación de contraseña y sesiones firmadas.

A completar en desarrollo. Ver reglas en CLAUDE.md §6 (Seguridad):
- Comparación segura de contraseña (hash; nunca en claro en logs).
- Cookie de sesión firmada con SESSION_SECRET (HttpOnly, SameSite=Strict, Secure en prod).
- Expiración de sesión y rate-limit en /login.
"""

from __future__ import annotations


def verify_password(plain: str, expected: str) -> bool:
    """Compara la contraseña ingresada contra la configurada (tiempo constante)."""
    raise NotImplementedError


def issue_session(secret: str) -> str:
    """Genera un token de sesión firmado."""
    raise NotImplementedError


def validate_session(token: str, secret: str) -> bool:
    """Valida un token de sesión."""
    raise NotImplementedError
