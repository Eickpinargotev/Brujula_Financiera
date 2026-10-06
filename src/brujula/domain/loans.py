"""Conciliacion FIFO de prestamos a partir del historial de movimientos.

No se guarda un saldo mutable: se reconstruye cronologicamente. Asi editar o borrar un
movimiento antiguo corrige automaticamente todos los estados posteriores.
"""

from __future__ import annotations

import unicodedata
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, TypedDict


class LoanMovement(Protocol):
    id: int
    tipo: str
    monto: float
    descripcion: str
    sobre: str | None
    fuente_ingreso: str | None


class LoanInfo(TypedDict):
    persona: str
    rol: Literal["pago", "prestamo"]
    direccion: Literal["cobrar", "pagar"]
    aplicado: float
    original: float
    saldo: float
    estado: Literal["aplicado", "pendiente", "pagado", "abonado"]


@dataclass
class _Lot:
    movement_id: int
    tipo: str
    original: float
    remaining: float


def normalize(value: str) -> str:
    """Normaliza nombres/categorias para emparejar mayusculas, espacios y acentos."""
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return " ".join(ascii_value.casefold().split())


def is_loan_category(value: str | None) -> bool:
    """Reconoce prestamo/prestamos con o sin tilde y diferencias de mayusculas."""
    return bool(value and normalize(value).startswith("prestamo"))


def is_loan_movement(movement: LoanMovement) -> bool:
    category = movement.sobre if movement.tipo == "gasto" else movement.fuente_ingreso
    return is_loan_category(category)


def reconcile(movements: Sequence[LoanMovement]) -> dict[int, LoanInfo]:
    """Concilia por persona y FIFO; la entrada debe venir en orden fecha/id ascendente.

    Un gasto abre dinero por cobrar y un ingreso abre dinero por pagar. Un movimiento
    contrario cancela los lotes mas antiguos. El dominio conserva cualquier excedente
    como saldo inverso para que el adaptador pueda detectarlo y pedir que se separe.
    """
    queues: dict[str, deque[_Lot]] = {}
    result: dict[int, LoanInfo] = {}

    for mov in movements:
        if not is_loan_movement(mov):
            continue
        person = " ".join(mov.descripcion.split())
        key = normalize(person)
        if not key:
            continue
        queue = queues.setdefault(key, deque())
        amount = round(float(mov.monto), 2)
        left = amount
        applied = 0.0

        while left > 0.005 and queue and queue[0].tipo != mov.tipo:
            lot = queue[0]
            paid = min(left, lot.remaining)
            lot.remaining = round(lot.remaining - paid, 2)
            left = round(left - paid, 2)
            applied = round(applied + paid, 2)
            if lot.remaining <= 0.005:
                lot.remaining = 0.0
                queue.popleft()

        opened = left
        if opened > 0.005:
            queue.append(_Lot(mov.id, mov.tipo, opened, opened))

        result[mov.id] = {
            "persona": person,
            "rol": "pago" if applied > 0.005 and opened <= 0.005 else "prestamo",
            "direccion": "cobrar" if mov.tipo == "gasto" else "pagar",
            "aplicado": applied,
            "original": opened,
            "saldo": opened,
            "estado": "aplicado" if applied > 0.005 and opened <= 0.005 else "pendiente",
        }

    # Los pagos posteriores ya mutaron los lotes: reflejar el saldo final en el movimiento
    # que abrio cada deuda y marcar los que quedaron completamente saldados.
    outstanding = {lot.movement_id: lot.remaining for q in queues.values() for lot in q}
    for movement_id, info in result.items():
        if info["original"] <= 0.005:
            continue
        remaining = round(outstanding.get(movement_id, 0.0), 2)
        info["saldo"] = remaining
        if remaining <= 0.005:
            info["estado"] = "pagado"
        elif remaining < info["original"]:
            info["estado"] = "abonado"

    return result


def balances(metadata: Mapping[int, LoanInfo]) -> tuple[float, float]:
    """Devuelve (por_cobrar, por_pagar) sumando solo lotes actualmente pendientes."""
    receivable = payable = 0.0
    for info in metadata.values():
        remaining = info["saldo"]
        if remaining <= 0.005:
            continue
        if info["direccion"] == "cobrar":
            receivable += remaining
        else:
            payable += remaining
    return round(receivable, 2), round(payable, 2)
