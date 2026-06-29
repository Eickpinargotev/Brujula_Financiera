"""Bot de Telegram (python-telegram-bot, polling).

Se arranca desde el lifespan de FastAPI (mismo event loop, un solo proceso). Seguridad:
solo se registran handlers para `TELEGRAM_ALLOWED_CHAT_ID`; el resto se ignora en silencio.
"""

from __future__ import annotations

import logging

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from brujula.agent.graph import build_agent
from brujula.bot.handlers import on_start, on_text, on_voice
from brujula.config.settings import Settings

logger = logging.getLogger(__name__)


async def start_bot(settings: Settings) -> Application:
    """Construye el agente, arma el bot, aplica auth por chat_id e inicia el polling."""
    agent = build_agent()

    app = Application.builder().token(settings.telegram_bot_token).build()
    app.bot_data["agent"] = agent
    app.bot_data["settings"] = settings

    allowed = settings.telegram_allowed_chat_id
    if allowed is None:
        logger.warning("TELEGRAM_ALLOWED_CHAT_ID no configurado: el bot ignorará a todos.")
    # Filtro de chat: solo el dueño. Lista vacía => no atiende a nadie (silencio).
    chat_filter = filters.Chat(chat_id=allowed if allowed is not None else [])

    app.add_handler(CommandHandler("start", on_start, filters=chat_filter))
    app.add_handler(MessageHandler(chat_filter & filters.VOICE, on_voice))
    app.add_handler(MessageHandler(chat_filter & filters.TEXT & ~filters.COMMAND, on_text))

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    logger.info("Bot de Telegram iniciado (polling).")
    return app


async def stop_bot(app: Application) -> None:
    """Detiene el polling y apaga el bot limpiamente."""
    if app.updater is not None:
        await app.updater.stop()
    await app.stop()
    await app.shutdown()
    logger.info("Bot de Telegram detenido.")
