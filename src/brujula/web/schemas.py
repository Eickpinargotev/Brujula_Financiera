"""Esquemas de entrada de la API web (validación con Pydantic)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class MovimientoIn(BaseModel):
    """Alta manual de un movimiento desde el dashboard.

    `categoria` es el nombre que usa la UI para el sobre de gasto.
    """

    tipo: Literal["gasto", "ingreso"]
    monto: float = Field(gt=0)
    fecha: date
    descripcion: str = Field(min_length=1, max_length=200)
    account_id: int = Field(gt=0)
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


def _nombre_categoria(v: str) -> str:
    """Normaliza el nombre de una categoría (minúsculas, espacios colapsados)."""
    v = " ".join(v.split()).lower()
    if not v:
        raise ValueError("El nombre no puede estar vacío.")
    return v


class CategoriaIn(BaseModel):
    """Alta de una categoría de gasto (tabla `envelopes`).

    `tipo` define el tope mensual: 'porcentaje' del ingreso, 'fijo' en dólares o
    'residual' (lo que sobra → ahorro). Sin tope = 'fijo' con valor 0.
    """

    nombre: str = Field(min_length=1, max_length=30)
    tipo: Literal["porcentaje", "fijo", "residual"] = "fijo"
    valor: float = Field(default=0.0, ge=0)

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str) -> str:
        return _nombre_categoria(v)

    @field_validator("valor")
    @classmethod
    def _valor(cls, v: float) -> float:
        return round(v, 4)


class CategoriaUpdate(BaseModel):
    """Edición parcial de una categoría."""

    nombre: str | None = Field(default=None, min_length=1, max_length=30)
    tipo: Literal["porcentaje", "fijo", "residual"] | None = None
    valor: float | None = Field(default=None, ge=0)

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str | None) -> str | None:
        return _nombre_categoria(v) if v is not None else None

    @field_validator("valor")
    @classmethod
    def _valor(cls, v: float | None) -> float | None:
        return round(v, 4) if v is not None else None


class FuenteIn(BaseModel):
    """Alta de una categoría de ingreso (tabla `income_sources`). Solo nombre: sin tope."""

    nombre: str = Field(min_length=1, max_length=30)

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str) -> str:
        return _nombre_categoria(v)


class FuenteUpdate(BaseModel):
    """Edición (renombrado) de una categoría de ingreso."""

    nombre: str | None = Field(default=None, min_length=1, max_length=30)

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str | None) -> str | None:
        return _nombre_categoria(v) if v is not None else None


def _nombre_cuenta(v: str) -> str:
    v = " ".join(v.split())
    if not v:
        raise ValueError("El nombre no puede estar vacío.")
    return v


class CuentaIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=60)
    moneda: str = Field(default="USD", min_length=1, max_length=8)

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str) -> str:
        return _nombre_cuenta(v)

    @field_validator("moneda")
    @classmethod
    def _moneda(cls, v: str) -> str:
        return v.strip().upper()


class CuentaUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=60)
    activa: bool | None = None

    @field_validator("nombre")
    @classmethod
    def _nombre(cls, v: str | None) -> str | None:
        return _nombre_cuenta(v) if v is not None else None


class ConciliacionIn(BaseModel):
    saldo_real: float
    fecha: date
    descripcion: str = Field(default="Conciliación de saldo real", min_length=1, max_length=200)

    @field_validator("saldo_real")
    @classmethod
    def _saldo(cls, v: float) -> float:
        return round(v, 2)

    @field_validator("descripcion")
    @classmethod
    def _descripcion(cls, v: str) -> str:
        return _nombre_cuenta(v)


class TransferenciaIn(BaseModel):
    source_account_id: int = Field(gt=0)
    destination_account_id: int = Field(gt=0)
    fecha: date
    monto: float = Field(gt=0)
    descripcion: str = Field(min_length=1, max_length=200)

    @field_validator("monto")
    @classmethod
    def _monto(cls, v: float) -> float:
        return round(v, 2)

    @field_validator("descripcion")
    @classmethod
    def _descripcion(cls, v: str) -> str:
        return _nombre_cuenta(v)


class ParametrosIn(BaseModel):
    """Parámetros financieros editables desde Configuración (todos opcionales)."""

    base_salary: float | None = Field(default=None, ge=0)
    iess_personal_rate: float | None = Field(default=None, ge=0, le=1)
    income_tax_monthly: float | None = Field(default=None, ge=0)
    extra_income_baseline: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=1, max_length=8)

    @field_validator("currency")
    @classmethod
    def _currency(cls, v: str | None) -> str | None:
        v = _limpiar_opcional(v)
        return v.upper() if v else None


class MetaIn(BaseModel):
    """Alta de una meta de ahorro (cascada por prioridad)."""

    nombre: str = Field(min_length=1, max_length=40)
    monto_objetivo: float = Field(gt=0)
    prioridad: int | None = Field(default=None, ge=1)  # None → al final de la cola
    emoji: str | None = Field(default=None, max_length=8)
    edad_objetivo: int | None = Field(default=None, ge=0, le=120)
    fecha_objetivo: date | None = None
    # Compromiso de ahorro mensual: manda la fecha estimada (None → ahorro promedio).
    ahorro_mensual: float | None = Field(default=None, gt=0)

    @field_validator("monto_objetivo", "ahorro_mensual")
    @classmethod
    def _redondear(cls, v: float | None) -> float | None:
        return round(v, 2) if v is not None else None

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
    ahorro_mensual: float | None = Field(default=None, gt=0)
    # Sentinelas para poder BORRAR la fecha objetivo / el compromiso mensual.
    limpiar_fecha: bool = False
    limpiar_ahorro: bool = False
