"""Esquemas de entrada de la API web (validación con Pydantic)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class MovimientoIn(BaseModel):
    """Alta manual de un movimiento desde el dashboard."""

    tipo: Literal["gasto", "ingreso"]
    monto: float = Field(gt=0)
    fecha: date
    descripcion: str = Field(min_length=1, max_length=200)
    sobre: str | None = None
    categoria: str | None = None
    fuente_ingreso: str | None = None
    comercio: str | None = None

    @field_validator("monto")
    @classmethod
    def _redondear(cls, v: float) -> float:
        return round(v, 2)

    @field_validator("descripcion")
    @classmethod
    def _limpiar(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("La descripción no puede estar vacía.")
        return v

    @field_validator("sobre", "categoria", "fuente_ingreso", "comercio")
    @classmethod
    def _vacio_a_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


def _limpiar_opcional(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v or None


class MetaIn(BaseModel):
    """Alta de una meta de ahorro (cascada por prioridad)."""

    nombre: str = Field(min_length=1, max_length=40)
    monto_objetivo: float = Field(gt=0)
    prioridad: int | None = Field(default=None, ge=1)  # None → al final de la cola
    emoji: str | None = Field(default=None, max_length=8)
    edad_objetivo: int | None = Field(default=None, ge=0, le=120)
    fecha_objetivo: date | None = None

    @field_validator("monto_objetivo")
    @classmethod
    def _redondear(cls, v: float) -> float:
        return round(v, 2)

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("El nombre no puede estar vacío.")
        return v

    @field_validator("emoji")
    @classmethod
    def _emoji(cls, v: str | None) -> str | None:
        return _limpiar_opcional(v)


class MetaUpdate(BaseModel):
    """Edición parcial de una meta (todos los campos opcionales)."""

    nombre: str | None = Field(default=None, min_length=1, max_length=40)
    monto_objetivo: float | None = Field(default=None, gt=0)
    prioridad: int | None = Field(default=None, ge=1)
    emoji: str | None = Field(default=None, max_length=8)
    edad_objetivo: int | None = Field(default=None, ge=0, le=120)
    fecha_objetivo: date | None = None
    # Sentinela para poder BORRAR la fecha objetivo (dejar la meta sin límite).
    limpiar_fecha: bool = False
