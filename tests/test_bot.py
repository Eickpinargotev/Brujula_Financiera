"""Pruebas de humo del bot (importación e integración básica, sin red)."""

from __future__ import annotations


def test_bot_modules_import() -> None:
    from brujula.bot import handlers, telegram_bot

    assert callable(telegram_bot.start_bot)
    assert callable(telegram_bot.stop_bot)
    assert callable(handlers.on_text)
    assert callable(handlers.on_voice)
    assert callable(handlers.on_start)


def test_welcome_message_is_present() -> None:
    from brujula.bot.handlers import _WELCOME

    assert "copiloto financiero" in _WELCOME
