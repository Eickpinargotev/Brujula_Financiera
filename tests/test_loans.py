"""Pruebas de la conciliacion pura de prestamos."""

from __future__ import annotations

from dataclasses import dataclass

from brujula.domain.loans import balances, reconcile


@dataclass
class Mov:
    id: int
    tipo: str
    monto: float
    descripcion: str
    sobre: str | None = None
    fuente_ingreso: str | None = None


def test_fifo_salda_primero_el_lote_mas_antiguo() -> None:
    movs = [
        Mov(1, "gasto", 5, "Billy", sobre="préstamos"),
        Mov(2, "gasto", 7, "billy", sobre="prestamo"),
        Mov(3, "ingreso", 10, " BILLY ", fuente_ingreso="Préstamo"),
    ]
    result = reconcile(movs)
    assert result[1]["estado"] == "pagado"
    assert result[2]["estado"] == "abonado"
    assert result[2]["saldo"] == 2.0
    assert result[3]["estado"] == "aplicado"
    assert balances(result) == (2.0, 0.0)


def test_saldos_de_personas_distintas_no_se_mezclan() -> None:
    movs = [
        Mov(1, "gasto", 9, "Billy", sobre="prestamo"),
        Mov(2, "ingreso", 9, "Janaina", fuente_ingreso="prestamo"),
    ]
    assert balances(reconcile(movs)) == (9.0, 9.0)


def test_excedente_abre_saldo_en_direccion_contraria() -> None:
    movs = [
        Mov(1, "gasto", 5, "Billy", sobre="prestamo"),
        Mov(2, "ingreso", 8, "Billy", fuente_ingreso="prestamo"),
    ]
    result = reconcile(movs)
    assert result[1]["estado"] == "pagado"
    assert result[2]["aplicado"] == 5.0
    assert result[2]["saldo"] == 3.0
    assert balances(result) == (0.0, 3.0)
