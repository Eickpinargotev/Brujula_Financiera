"""Handlers de Telegram. A completar en desarrollo.

- mensaje de voz  -> services.transcription (Scribe v2) -> agente
    Tras transcribir, se responde citando el audio y se anexa la línea de uso
    (services.usage.format_usage_line): "⏱ <duración> · 💳 <créditos>".
- mensaje de texto -> agente
- comandos: /start, /reporte, /metas, /saldo
Todos pasan por el filtro de chat_id permitido (telegram_allowed_chat_id).
"""

from __future__ import annotations
