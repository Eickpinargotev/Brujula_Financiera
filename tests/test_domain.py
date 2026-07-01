"""Pruebas de la lógica financiera pura (domain/budget, goals, forecast)."""

from __future__ import annotations

from datetime import date

from brujula.domain import budget, forecast
from brujula.domain import goals as goals_dom

# --- budget -------------------------------------------------------------------------


def test_allocation_porcentaje() -> None:
    assert budget.allocation("porcentaje", 0.10, 1500.0) == 150.0


def test_allocation_fijo() -> None:
    assert budget.allocation("fijo", 60.0, 1500.0) == 60.0


def test_allocation_residual_es_cero() -> None:
    assert budget.allocation("residual", 0.0, 1500.0) == 0.0


def test_residual_allocation() -> None:
    assert budget.residual_allocation(1500.0, 460.0) == 1040.0
    # nunca negativo
    assert budget.residual_allocation(500.0, 800.0) == 0.0


def test_semaforo_verde() -> None:
    assert budget.semaforo(100.0, 20.0) == "verde"


def test_semaforo_amarillo() -> None:
    # disponible 10 < 15% de 100 → amarillo
    assert budget.semaforo(100.0, 90.0) == "amarillo"


def test_semaforo_rojo() -> None:
    assert budget.semaforo(100.0, 130.0) == "rojo"


def test_semaforo_sin_asignacion() -> None:
    assert budget.semaforo(0.0, 0.0) == "verde"
    assert budget.semaforo(0.0, 5.0) == "rojo"


# --- goals --------------------------------------------------------------------------


def test_progreso() -> None:
    assert goals_dom.progreso(27000.0, 5400.0) == 0.2
    assert goals_dom.progreso(100.0, 0.0) == 0.0
    assert goals_dom.progreso(100.0, 250.0) == 1.0  # se topa en 1
    assert goals_dom.progreso(0.0, 10.0) == 0.0


def test_restante() -> None:
    assert goals_dom.restante(27000.0, 5000.0) == 22000.0
    assert goals_dom.restante(100.0, 250.0) == 0.0


def test_ahorro_necesario() -> None:
    assert goals_dom.ahorro_necesario(2400.0, 12) == 200.0
    assert goals_dom.ahorro_necesario(2400.0, 0) == 2400.0


def test_asignar_cascada_llena_por_prioridad() -> None:
    # pool 9500 → carro (27000) recibe todo, casa (100000) queda en 0
    asignados, libre = goals_dom.asignar_cascada(9500.0, [27000.0, 100000.0])
    assert asignados == [9500.0, 0.0]
    assert libre == 0.0


def test_asignar_cascada_desborda_a_la_siguiente() -> None:
    # pool 30000 → carro completo (27000), casa recibe 3000
    asignados, libre = goals_dom.asignar_cascada(30000.0, [27000.0, 100000.0])
    assert asignados == [27000.0, 3000.0]
    assert libre == 0.0


def test_asignar_cascada_sobrante_libre() -> None:
    asignados, libre = goals_dom.asignar_cascada(5000.0, [1000.0, 2000.0])
    assert asignados == [1000.0, 2000.0]
    assert libre == 2000.0


def test_meses_hasta_objetivo() -> None:
    # faltan 2000 desde un pool de 500 (objetivo acumulado 2500), a 500/mes → 4 meses
    assert goals_dom.meses_hasta_objetivo(500.0, 2500.0, 500.0) == 4
    assert goals_dom.meses_hasta_objetivo(3000.0, 2500.0, 500.0) == 0  # ya alcanzado
    assert goals_dom.meses_hasta_objetivo(500.0, 2500.0, 0.0) is None  # sin ahorro


# --- forecast -----------------------------------------------------------------------


def test_meses_entre() -> None:
    assert forecast.meses_entre(date(2026, 1, 1), date(2026, 7, 1)) == 6
    assert forecast.meses_entre(date(2026, 1, 1), date(2026, 1, 15)) == 1  # días sueltos
    assert forecast.meses_entre(date(2026, 7, 1), date(2026, 1, 1)) == 0  # nunca negativo


def test_edad_en() -> None:
    assert forecast.edad_en(date(1998, 2, 20), date(2028, 2, 20)) == (30, 0)
    assert forecast.edad_en(date(1998, 2, 20), date(2028, 6, 20)) == (30, 4)


def test_fecha_proyectada_con_ahorro() -> None:
    # 1000 restante a 250/mes → 4 meses
    assert forecast.fecha_proyectada(1000.0, 250.0, date(2026, 1, 1)) == date(2026, 5, 1)


def test_fecha_proyectada_sin_ahorro() -> None:
    assert forecast.fecha_proyectada(1000.0, 0.0, date(2026, 1, 1)) is None


def test_fecha_proyectada_ya_alcanzada() -> None:
    hoy = date(2026, 1, 1)
    assert forecast.fecha_proyectada(0.0, 250.0, hoy) == hoy


def test_simular_aumento_adelanta_meta() -> None:
    hoy = date(2026, 1, 1)
    r = forecast.simular_aumento(1200.0, 100.0, 100.0, hoy)
    # 1200/100 = 12 meses; 1200/200 = 6 meses → adelanta 6
    assert r["meses_ahorrados"] == 6


def test_proyeccion_saldo() -> None:
    assert forecast.proyeccion_saldo(1000.0, 500.0, 3) == [1000.0, 1500.0, 2000.0, 2500.0]
