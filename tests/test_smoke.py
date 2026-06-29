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


def test_missing_required_detecta_faltantes() -> None:
    """Sin secretos, lista todas las variables requeridas que faltan.

    Se pasan vacías explícitamente (en el contenedor el entorno trae el .env real).
    """
    s = Settings(
        app_env="production",
        telegram_bot_token="",
        telegram_allowed_chat_id="",
        openai_api_key="",
        elevenlabs_api_key="",
        dashboard_password="",
        session_secret="",
    )
    assert set(s.missing_required()) == {
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_ALLOWED_CHAT_ID",
        "OPENAI_API_KEY",
        "ELEVENLABS_API_KEY",
        "DASHBOARD_PASSWORD",
        "SESSION_SECRET",
    }


def test_missing_required_vacio_con_todo_configurado() -> None:
    s = Settings(
        app_env="production",
        telegram_bot_token="t",
        telegram_allowed_chat_id="1",
        openai_api_key="k",
        elevenlabs_api_key="e",
        dashboard_password="p",
        session_secret="s",
    )
    assert s.missing_required() == []
