"""Pruebas de la extracción de costo desde headers (sin red)."""

from __future__ import annotations

from brujula.services.transcription import extract_cost_from_headers


def test_extract_cost_known_header() -> None:
    assert extract_cost_from_headers({"character-cost": "1500"}) == 1500


def test_extract_cost_case_insensitive() -> None:
    assert extract_cost_from_headers({"XI-Cost": "42"}) == 42


def test_extract_cost_float_value() -> None:
    assert extract_cost_from_headers({"xi-credits-usage": "12.0"}) == 12


def test_extract_cost_missing_returns_minus_one() -> None:
    assert extract_cost_from_headers({"content-type": "application/json"}) == -1


def test_extract_cost_non_numeric_returns_minus_one() -> None:
    assert extract_cost_from_headers({"xi-cost": "n/a"}) == -1
