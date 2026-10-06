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
    """Meta de ahorro pagada a contado (carro, casa, dron…).

    Las metas se financian en **cascada por prioridad**: todo el ahorro se acumula en la
    meta de menor `prioridad` (1 = primera) hasta completarla; luego pasa a la siguiente.
    Por eso `ahorrado` NO se guarda: se deriva del profit total repartido por prioridad.

    La fecha objetivo es **opcional** y solo informativa: puede venir de `edad_objetivo`
    (nacimiento + edad) o de `fecha_objetivo` (fecha exacta); si ambas son nulas, la meta
    no tiene fecha límite y solo se muestra la fecha estimada según el ritmo de ahorro.

    `ahorro_mensual` es el compromiso mensual fijado por el dueño: cuando existe, la fecha
    estimada se calcula con él (meses = faltante ÷ compromiso); si es None se usa el
    ahorro promedio real. Cada cambio de compromiso queda registrado en `goal_commitments`.
    """

    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String, unique=True)
    monto_objetivo: Mapped[float] = mapped_column(Float)
    prioridad: Mapped[int] = mapped_column(Integer, default=100)  # 1 = primera en la cola
    emoji: Mapped[str | None] = mapped_column(String, nullable=True)
    edad_objetivo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fecha_objetivo: Mapped[date | None] = mapped_column(Date, nullable=True)
    ahorro_mensual: Mapped[float | None] = mapped_column(Float, nullable=True)
    # default (cliente) además de server_default: la tabla migrada con ALTER no tiene
    # default SQL (SQLite no acepta CURRENT_TIMESTAMP en ADD COLUMN).
    creada_en: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now()
    )


class GoalCommitment(Base):
    """Hito del compromiso de ahorro de una meta (historial de la fecha objetivo).

    Se inserta cada vez que el dueño fija o cambia `ahorro_mensual`: guarda una foto del
    momento (cuánto llevaba ahorrado, meses estimados y fecha estimada con el nuevo
    compromiso) para ver cómo la fecha objetivo fue bajando con el tiempo.
    """

    __tablename__ = "goal_commitments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"))
    fecha: Mapped[date] = mapped_column(Date)
    ahorro_mensual: Mapped[float] = mapped_column(Float)
    ahorrado: Mapped[float] = mapped_column(Float, default=0.0)
    meses_estimados: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fecha_estimada: Mapped[date | None] = mapped_column(Date, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


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


class IncomeSource(Base):
    """Categoría de ingreso (el dato en `movimientos.fuente_ingreso`).

    Espejo de `Envelope` para el otro lado del flujo: los gastos se clasifican por sobre,
    los ingresos por fuente. No lleva tope ni tipo: el ingreso no se presupuesta.
    """

    __tablename__ = "income_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String, unique=True)


class Account(Base):
    """Lugar real donde se mantiene dinero (banco, billetera o exchange)."""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String, unique=True)
    moneda: Mapped[str] = mapped_column(String, default="USD")
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    creada_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Operacion(Base):
    """Compra/operación que agrupa varios movimientos (ítem + impuestos + envío)."""

    __tablename__ = "operaciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String)
    fecha: Mapped[date] = mapped_column(Date)
    descripcion: Mapped[str | None] = mapped_column(String, nullable=True)


class Movimiento(Base):
    """Movimiento de dinero: gasto o ingreso (modelo unificado).

    En gastos se usa `sobre` (la única clasificación); en ingresos, `fuente_ingreso`.
    """

    __tablename__ = "movimientos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tipo: Mapped[str] = mapped_column(String)  # 'gasto' | 'ingreso'
    fecha: Mapped[date] = mapped_column(Date)
    monto: Mapped[float] = mapped_column(Float)
    descripcion: Mapped[str] = mapped_column(String)

    # Solo en gastos:
    sobre: Mapped[str | None] = mapped_column(String, nullable=True)
    # Solo en ingresos:
    fuente_ingreso: Mapped[str | None] = mapped_column(String, nullable=True)
    # Ambos:
    comercio: Mapped[str | None] = mapped_column(String, nullable=True)
    # Nullable en bases migradas por compatibilidad de SQLite; la API exige una cuenta.
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id"), nullable=True, index=True
    )
    grupo_id: Mapped[int | None] = mapped_column(ForeignKey("operaciones.id"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AccountAdjustment(Base):
    """Ajuste auditable para conciliar el saldo calculado con el saldo real."""

    __tablename__ = "account_adjustments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    fecha: Mapped[date] = mapped_column(Date)
    monto: Mapped[float] = mapped_column(Float)  # delta firmado
    descripcion: Mapped[str] = mapped_column(String)
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Transfer(Base):
    """Movimiento interno entre cuentas; no es ingreso ni gasto."""

    __tablename__ = "transfers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    destination_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), index=True)
    fecha: Mapped[date] = mapped_column(Date)
    monto: Mapped[float] = mapped_column(Float)
    descripcion: Mapped[str] = mapped_column(String)
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
    comercio: Mapped[str | None] = mapped_column(String, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
