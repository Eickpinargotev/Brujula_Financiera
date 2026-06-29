"""Configuración SOLO de infraestructura y secretos.

Los parámetros financieros (sueldo, porcentajes, metas, fecha de nacimiento, saldos, zona
horaria, moneda) NO viven aquí ni en `.env`: están en la **base de datos** y se editan o
consultan en tiempo de ejecución (Telegram / dashboard). Aquí solo van credenciales,
identificadores de modelos y configuración de despliegue.

Ninguna otra parte del código debe leer `os.environ` directamente: todo pasa por aquí.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # --- Telegram ---
    telegram_bot_token: str = ""
    telegram_allowed_chat_id: int | None = None

    # --- OpenAI (agente) ---
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # --- ElevenLabs (transcripción Scribe v2, batch) ---
    elevenlabs_api_key: str = ""
    elevenlabs_stt_model: str = "scribe_v2"

    # --- Dashboard (seguridad) ---
    dashboard_password: str = ""
    session_secret: str = ""

    # --- Base de datos ---
    database_url: str = "sqlite+aiosqlite:////data/brujula.db"

    @field_validator("telegram_allowed_chat_id", mode="before")
    @classmethod
    def _empty_to_none(cls, v: object) -> object:
        """Trata una variable vacía ('') como None para no romper el arranque."""
        if v in ("", None):
            return None
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración (cacheada) de infraestructura."""
    return Settings()
