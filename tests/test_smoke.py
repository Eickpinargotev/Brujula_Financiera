"""Pruebas de humo del scaffolding. Se ejecutan en Docker: `make test`."""

from __future__ import annotations

from brujula.config.settings import Settings


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


def test_missing_required_detecta_faltantes() -> None:
    """Sin secretos, lista todas las variables requeridas que faltan.

    Se pasan vacías explícitamente (en el contenedor el entorno trae el .env real).
    """
    s = Settings(
        app_env="production",
        dashboard_password="",
        session_secret="",
    )
    assert set(s.missing_required()) == {
        "DASHBOARD_PASSWORD",
        "SESSION_SECRET",
    }


def test_missing_required_vacio_con_todo_configurado() -> None:
    s = Settings(
        app_env="production",
        dashboard_password="p",
        session_secret="s",
    )
    assert s.missing_required() == []
