"""Configuración SOLO de infraestructura y secretos.

Los parámetros financieros (sueldo, porcentajes, metas, fecha de nacimiento, saldos, zona
horaria, moneda) NO viven aquí ni en `.env`: están en la **base de datos** y se editan o
consultan en tiempo de ejecución desde el dashboard. Aquí solo van credenciales y
configuración de despliegue.

Ninguna otra parte del código debe leer `os.environ` directamente: todo pasa por aquí.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Variables que DEBEN estar presentes en producción (si falta una, no se inicia).
_REQUIRED_IN_PRODUCTION = (
    "dashboard_password",
    "session_secret",
)


class Settings(BaseSettings):
    """Configuración de infraestructura de Brújula Financiera (desde el entorno / .env)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Entorno / despliegue ---
    app_env: str = "development"

    # --- Dashboard (seguridad) ---
    dashboard_password: str = ""
    session_secret: str = ""

    # --- Base de datos ---
    database_url: str = "sqlite+aiosqlite:////data/brujula.db"
    # Solo para una instalación vacía deliberada; nunca habilitar en uso diario.
    allow_database_create: bool = False

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    def missing_required(self) -> list[str]:
        """Nombres (en MAYÚSCULAS) de variables requeridas que faltan o están vacías."""
        return [
            field.upper()
            for field in _REQUIRED_IN_PRODUCTION
            if getattr(self, field) in (None, "")
        ]


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración (cacheada) de infraestructura."""
    return Settings()
