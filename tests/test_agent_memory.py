"""Pruebas de la ventana de memoria (últimas 7 interacciones)."""

from __future__ import annotations

from brujula.agent.memory import MAX_INTERACTIONS, overflow, window


def test_window_keeps_last_pairs() -> None:
    msgs = list(range(20))
    w = window(msgs)
    assert len(w) == MAX_INTERACTIONS * 2
    assert w == list(range(6, 20))


def test_window_shorter_than_limit() -> None:
    assert window([1, 2, 3]) == [1, 2, 3]


def test_overflow_returns_excess() -> None:
    assert overflow(list(range(20))) == list(range(6))


def test_overflow_empty_when_within_limit() -> None:
    assert overflow([1, 2]) == []
