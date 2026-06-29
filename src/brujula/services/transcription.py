"""Transcripción voz→texto con ElevenLabs Scribe v2 (batch, NO realtime).

Usamos el endpoint síncrono `POST /v1/speech-to-text` (sin webhook, sin streaming):
es lo más simple y suficiente para notas de voz cortas, y evita la complejidad del
modo realtime (`scribe_v2_realtime`), que aquí no se necesita.

La duración se toma de `audio_duration_secs` del JSON de respuesta. El costo en créditos
NO está documentado en headers para STT, así que se escanea una lista de nombres de
header candidatos y, en el primer uso real, se loguean los headers recibidos para
descubrir el nombre correcto. Si no se encuentra, `cost_credits = -1` (se mostrará "n/d").
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

STT_ENDPOINT = "https://api.elevenlabs.io/v1/speech-to-text"

# Posibles headers donde ElevenLabs podría reportar el costo en créditos del STT.
# No está documentado; se prueban en orden. Ajustar cuando se confirme el real
# (ver el log DEBUG "ElevenLabs STT headers: ..." de la primera llamada).
_COST_HEADER_CANDIDATES: tuple[str, ...] = (
    "character-cost",
    "x-character-count",
    "x-character-cost",
    "x-usage-character-count",
    "xi-character-count",
    "xi-character-cost",
    "xi-cost",
    "xi-credits-usage",
    "xi-billing-credits",
)


class TranscriptionError(RuntimeError):
    """Falla al transcribir audio con ElevenLabs."""


@dataclass(slots=True)
class TranscriptionResult:
    """Resultado de una transcripción."""

    text: str
    duration_secs: float | None
    cost_credits: int  # -1 si la API no reportó el costo
    language_code: str | None


def extract_cost_from_headers(headers: httpx.Headers | dict[str, str]) -> int:
    """Devuelve el costo en créditos leído de los headers, o -1 si no aparece."""
    lowered = {str(k).lower(): v for k, v in dict(headers).items()}
    for name in _COST_HEADER_CANDIDATES:
        if name in lowered:
            try:
                return int(float(lowered[name]))
            except (TypeError, ValueError):
                continue
    return -1


async def transcribe(
    audio_bytes: bytes,
    *,
    api_key: str,
    model: str = "scribe_v2",
    filename: str = "audio.ogg",
    mime_type: str = "audio/ogg",
    diarize: bool = False,
    tag_audio_events: bool = False,
    language_code: str | None = None,
    timeout: float = 120.0,
) -> TranscriptionResult:
    """Transcribe un audio con ElevenLabs Scribe v2.

    `diarize=False` por defecto: las notas las dicta una sola persona, así que la
    diarización es innecesaria (y más costosa). `timestamps_granularity=none` para una
    respuesta más liviana (solo nos interesa el texto).
    """
    if not api_key:
        raise TranscriptionError("Falta ELEVENLABS_API_KEY.")
    if not audio_bytes:
        raise TranscriptionError("Audio vacío.")

    data: dict[str, str] = {
        "model_id": model,
        "diarize": str(diarize).lower(),
        "tag_audio_events": str(tag_audio_events).lower(),
        "timestamps_granularity": "none",
    }
    if language_code:
        data["language_code"] = language_code

    files = {"file": (filename, audio_bytes, mime_type)}
    headers = {"xi-api-key": api_key}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(STT_ENDPOINT, headers=headers, data=data, files=files)
    except httpx.HTTPError as exc:
        raise TranscriptionError(f"Error de red al transcribir: {exc}") from exc

    # Logueamos SOLO los nombres de headers (sin valores) para descubrir cuál
    # reporta el costo, sin filtrar datos sensibles.
    logger.debug("ElevenLabs STT headers: %s", sorted(resp.headers.keys()))

    if resp.status_code != 200:
        snippet = resp.text[:300] if resp.text else ""
        raise TranscriptionError(f"ElevenLabs respondió {resp.status_code}: {snippet}")

    try:
        payload = resp.json()
    except ValueError as exc:
        raise TranscriptionError("Respuesta no-JSON de ElevenLabs.") from exc

    text = (payload.get("text") or "").strip()
    if not text:
        raise TranscriptionError("La transcripción vino vacía.")

    return TranscriptionResult(
        text=text,
        duration_secs=payload.get("audio_duration_secs"),
        cost_credits=extract_cost_from_headers(resp.headers),
        language_code=payload.get("language_code"),
    )
