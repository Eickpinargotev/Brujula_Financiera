"""Handlers de Telegram. Conectan los mensajes del dueño con el agente.

- texto  → agente (`run_turn`)
- voz    → transcripción (Scribe v2) → agente; la respuesta cita el audio y anexa la
           línea de uso (⏱ duración · 💳 créditos)
- /start → bienvenida
Todos pasan ya filtrados por chat_id (ver telegram_bot.py).
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from brujula.agent.graph import run_turn
from brujula.services.transcription import TranscriptionError, transcribe
from brujula.services.usage import format_usage_line

logger = logging.getLogger(__name__)

_WELCOME = (
    "🧭 Hola, soy tu copiloto financiero.\n\n"
    "Dime un gasto o ingreso (texto o audio) y lo registro tras confirmarlo. "
    "Ejemplos: «gasté 53.90 con mi pareja en comida» o «hoy recibí 1500 del trabajo».\n"
    "También puedes preguntarme «¿cuánto gasté este mes?»."
)


async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(_WELCOME)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    agent = context.bot_data["agent"]
    reply = await run_turn(agent, str(update.effective_chat.id), update.message.text or "")
    await update.message.reply_text(reply)


async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.voice or not update.effective_chat:
        return
    agent = context.bot_data["agent"]
    settings = context.bot_data["settings"]

    try:
        tg_file = await context.bot.get_file(update.message.voice.file_id)
        audio = bytes(await tg_file.download_as_bytearray())
        result = await transcribe(
            audio,
            api_key=settings.elevenlabs_api_key,
            model=settings.elevenlabs_stt_model,
            filename="audio.oga",
            mime_type="audio/ogg",
        )
    except TranscriptionError as exc:
        logger.warning("Transcripción falló: %s", exc)
        await update.message.reply_text("No pude transcribir el audio 😕. ¿Me lo escribes?")
        return

    reply = await run_turn(agent, str(update.effective_chat.id), result.text)
    usage = format_usage_line(result.duration_secs, result.cost_credits)
    await update.message.reply_text(f'🎤 "{result.text}"\n\n{reply}\n\n{usage}')
