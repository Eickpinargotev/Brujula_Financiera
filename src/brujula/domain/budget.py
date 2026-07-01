"""Presupuesto por sobres: asignación mensual y semáforo. Lógica pura (sin IO).

Ver docs/finance-model.md §2. El dinero NO se calcula en el LLM ni en la UI: aquí.
"""

from __future__ import annotations

# Si el saldo disponible de un sobre cae por debajo de este % de lo asignado,
# se considera "cerca del tope" → semáforo amarillo.
YELLOW_THRESHOLD = 0.15


def allocation(tipo: str, valor: float, ingreso_total: float) -> float:
    """Asignación mensual de un sobre según su tipo.

    - 'porcentaje': fracción del ingreso TOTAL del mes (escala con los ingresos).
    - 'fijo': monto fijo en dólares.
    - 'residual': 0 aquí; se calcula aparte con `residual_allocation`.
    """
    if tipo == "porcentaje":
        return ingreso_total * valor
    if tipo == "fijo":
        return valor
    return 0.0


def residual_allocation(ingreso_total: float, asignaciones_no_residuales: float) -> float:
    """Lo que queda del ingreso tras cubrir sobres de porcentaje y fijos (→ ahorro/metas)."""
    return max(ingreso_total - asignaciones_no_residuales, 0.0)


def semaforo(asignado: float, gastado: float) -> str:
    """Estado del sobre comparando lo gastado contra lo asignado.

    🟢 'verde' (vas bien) · 🟡 'amarillo' (cerca del tope) · 🔴 'rojo' (te pasaste).
    """
    if asignado <= 0:
        return "verde" if gastado <= 0 else "rojo"
    balance = asignado - gastado
    if balance < 0:
        return "rojo"
    if balance < asignado * YELLOW_THRESHOLD:
        return "amarillo"
    return "verde"
