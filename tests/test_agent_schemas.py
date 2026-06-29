"""Pruebas del guardián (esquemas Pydantic del agente)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from brujula.agent.schemas import (
    AgentDecision,
    Categoria,
    GastoDraft,
    Intent,
    Sobre,
)


def test_gasto_draft_valido() -> None:
    g = GastoDraft(monto=53.90, sobre="pareja", categoria="comida", descripcion="salida")
    assert g.sobre is Sobre.pareja
    assert g.categoria is Categoria.comida
    assert g.fecha is None  # se resolverá a hoy


def test_gasto_monto_debe_ser_positivo() -> None:
    with pytest.raises(ValidationError):
        GastoDraft(monto=0, sobre="pareja", categoria="comida", descripcion="x")


def test_gasto_sobre_invalido_rechazado() -> None:
    with pytest.raises(ValidationError):
        GastoDraft(monto=5, sobre="cripto", categoria="comida", descripcion="x")


def test_decision_defaults() -> None:
    d = AgentDecision(intent=Intent.otro, mensaje="hola")
    assert d.faltan_campos == []
    assert d.necesita_aclaracion is False
    assert d.gasto is None
