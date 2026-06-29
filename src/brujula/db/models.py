"""Modelos SQLAlchemy (esquema de la base de datos).

Aquí viven TODOS los datos: parámetros, metas, sobres, movimientos (gastos e ingresos
unificados), operaciones (compras agrupadas) y recurrentes. Nada de esto está en `.env`.
Ver docs/finance-model.md §6.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base declarativa de todos los modelos."""


class Parameter(Base):
    """Parámetro clave-valor (fecha nacimiento, sueldo, tasa IESS, zona horaria…)."""

    __tablename__ = "parameters"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(String, nullable=True)


class Goal(Base):
    """Meta de ahorro pagada a contado (carro, casa)."""

    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String, unique=True)
    monto_objetivo: Mapped[float] = mapped_column(Float)
    edad_objetivo: Mapped[int] = mapped_column(Integer)  # fecha = nacimiento + edad
    ahorrado: Mapped[float] = mapped_column(Float, default=0.0)


class Envelope(Base):
    """Sobre/presupuesto: define el destino del dinero y su tope mensual.

    tipo: 'porcentaje' (del ingreso total), 'fijo' (monto) o 'residual' (el resto → ahorro).
    """

    __tablename__ = "envelopes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String, unique=True)
    tipo: Mapped[str] = mapped_column(String)  # 'porcentaje' | 'fijo' | 'residual'
    valor: Mapped[float] = mapped_column(Float)  # fracción (0.10), monto fijo o 0
    arrastre: Mapped[bool] = mapped_column(Boolean, default=True)


class Operacion(Base):
    """Compra/operación que agrupa varios movimientos (ítem + impuestos + envío)."""

    __tablename__ = "operaciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String)
    fecha: Mapped[date] = mapped_column(Date)
    descripcion: Mapped[str | None] = mapped_column(String, nullable=True)


class Movimiento(Base):
    """Movimiento de dinero: gasto o ingreso (modelo unificado).

    En gastos se usan `sobre` y `categoria`; en ingresos, `fuente_ingreso`.
    """

    __tablename__ = "movimientos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tipo: Mapped[str] = mapped_column(String)  # 'gasto' | 'ingreso'
    fecha: Mapped[date] = mapped_column(Date)
    monto: Mapped[float] = mapped_column(Float)
    descripcion: Mapped[str] = mapped_column(String)

    # Solo en gastos:
    sobre: Mapped[str | None] = mapped_column(String, nullable=True)
    categoria: Mapped[str | None] = mapped_column(String, nullable=True)
    # Solo en ingresos:
    fuente_ingreso: Mapped[str | None] = mapped_column(String, nullable=True)
    # Ambos:
    comercio: Mapped[str | None] = mapped_column(String, nullable=True)
    grupo_id: Mapped[int | None] = mapped_column(ForeignKey("operaciones.id"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Recurrente(Base):
    """Cargo recurrente para pronóstico (suscripciones como Shopify, con impuestos)."""

    __tablename__ = "recurrentes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String, unique=True)
    monto_base: Mapped[float] = mapped_column(Float)
    iva: Mapped[float] = mapped_column(Float, default=0.0)  # fracción, ej. 0.15
    isd: Mapped[float] = mapped_column(Float, default=0.0)  # fracción, ej. 0.05
    periodicidad: Mapped[str] = mapped_column(String, default="mensual")
    sobre: Mapped[str | None] = mapped_column(String, nullable=True)
    categoria: Mapped[str | None] = mapped_column(String, nullable=True)
    comercio: Mapped[str | None] = mapped_column(String, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
