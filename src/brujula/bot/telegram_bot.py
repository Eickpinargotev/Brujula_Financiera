"""Arranque/parada del bot de Telegram (python-telegram-bot, polling).

A completar en desarrollo. Se inicia desde el lifespan de FastAPI (mismo event loop).

    async def start_bot(settings) -> Application: ...
    # registra handlers, aplica filtro por chat_id, inicia polling

Seguridad: descartar en silencio cualquier update de un chat_id distinto a
settings.telegram_allowed_chat_id.
"""

from __future__ import annotations
