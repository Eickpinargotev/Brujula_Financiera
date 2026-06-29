"""Pruebas de humo del scaffolding. Se ejecutan en Docker: `make test`."""

from __future__ import annotations

from brujula.config.settings import Settings


def test_empty_chat_id_becomes_none() -> None:
    """Un chat_id vacío no debe romper el arranque."""
    s = Settings(telegram_allowed_chat_id="")
    assert s.telegram_allowed_chat_id is None


def test_settings_has_no_financial_fields() -> None:
    """El .env/Settings NO debe contener parámetros financieros (viven en la BD)."""
    fields = set(Settings.model_fields)
    assert "base_salary" not in fields
    assert "meta_carro" not in fields
    assert "birth_date" not in fields


def test_app_imports() -> None:
    """La app de FastAPI se importa sin errores."""
    from brujula.main import app

    assert app.title == "Brújula Financiera"


def test_bot_no_hace_polling_en_desarrollo() -> None:
    """En desarrollo el bot NO debe hacer polling (evita conflicto con la nube)."""
    s = Settings(app_env="development", telegram_bot_token="t", openai_api_key="k")
    assert s.bot_should_poll is False


def test_bot_hace_polling_en_produccion_con_credenciales() -> None:
    s = Settings(app_env="production", telegram_bot_token="t", openai_api_key="k")
    assert s.bot_should_poll is True


def test_bot_no_polling_sin_credenciales() -> None:
    s = Settings(app_env="production", telegram_bot_token="", openai_api_key="k")
    assert s.bot_should_poll is False
