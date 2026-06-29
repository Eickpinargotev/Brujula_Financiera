"""Formato de la línea de uso (duración + costo en créditos) para Telegram.

Se anexa al final de cada transcripción, p.ej.:  "⏱ 0:12 · 💳 1.234 créditos"
"""

from __future__ import annotations


def format_duration(secs: float | int | None) -> str | None:
    """Formatea segundos a m:ss (o h:mm:ss). Devuelve None si no hay duración válida."""
    if not isinstance(secs, (int, float)) or secs <= 0:
        return None
    total = int(round(secs))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def format_usage_line(duration_secs: float | int | None, cost_credits: int | None) -> str:
    """Arma la línea '⏱ <dur> · 💳 <créditos>' con miles separados por punto."""
    parts: list[str] = []

    dur = format_duration(duration_secs)
    if dur:
        parts.append(f"⏱ {dur}")

    if isinstance(cost_credits, int) and cost_credits >= 0:
        parts.append(f"💳 {cost_credits:,} créditos".replace(",", "."))
    else:
        parts.append("💳 créditos: n/d")

    return " · ".join(parts)
