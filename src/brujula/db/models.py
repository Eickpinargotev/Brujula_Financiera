"""Modelos SQLAlchemy (esquema de la base de datos).

Aquí viven TODOS los datos: parámetros financieros, metas, sobres y movimientos.
Nada de esto está en `.env`. Ver docs/finance-model.md.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base declarativa de todos los modelos."""


class Parameter(Base):
    """Parámetro financiero/clave-valor (sueldo, tasa IESS, fecha nacimiento, etc.)."""

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
    """Sobre del presupuesto (familia, relación, iglesia…) con arrastre opcional."""

    __tablename__ = "envelopes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String, unique=True)
    tipo: Mapped[str] = mapped_column(String)  # 'fijo' | 'porcentaje'
    valor: Mapped[float] = mapped_column(Float)  # monto fijo o fracción (0.10)
    arrastre: Mapped[bool] = mapped_column(Boolean, default=True)


class Income(Base):
    """Ingreso registrado (trabajo o proyecto personal)."""

    __tablename__ = "incomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fecha: Mapped[date] = mapped_column(Date)
    monto: Mapped[float] = mapped_column(Float)
    fuente: Mapped[str] = mapped_column(String)  # 'trabajo' | 'proyecto_personal'
    descripcion: Mapped[str | None] = mapped_column(String, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Expense(Base):
    """Gasto registrado, asociado a una categoría y opcionalmente a un sobre."""

    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fecha: Mapped[date] = mapped_column(Date)
    monto: Mapped[float] = mapped_column(Float)
    categoria: Mapped[str] = mapped_column(String)
    sobre: Mapped[str | None] = mapped_column(String, nullable=True)
    descripcion: Mapped[str | None] = mapped_column(String, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
