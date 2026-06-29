"""Pruebas del formateo de la línea de uso (duración + créditos)."""

from __future__ import annotations

from brujula.services.usage import format_duration, format_usage_line


def test_format_duration_minutes_seconds() -> None:
    assert format_duration(12) == "0:12"
    assert format_duration(75) == "1:15"


def test_format_duration_with_hours() -> None:
    assert format_duration(3725) == "1:02:05"


def test_format_duration_invalid() -> None:
    assert format_duration(0) is None
    assert format_duration(None) is None


def test_usage_line_with_cost() -> None:
    line = format_usage_line(12, 1234)
    assert "⏱ 0:12" in line
    assert "💳 1.234 créditos" in line  # miles con punto


def test_usage_line_cost_unknown() -> None:
    line = format_usage_line(12, -1)
    assert "créditos: n/d" in line


def test_usage_line_no_duration() -> None:
    line = format_usage_line(None, 10)
    assert line == "💳 10 créditos"
