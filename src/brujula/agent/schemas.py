"""Esquemas estructurados del agente = el GUARDIÁN determinístico.

El LLM debe producir un `AgentDecision` que valida Pydantic. Si los tipos no calzan o
faltan campos requeridos, no se guarda nada: se le pregunta al usuario. Esto evita
alucinaciones y datos basura en la BD.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class Tipo(StrEnum):
    gasto = "gasto"
    ingreso = "ingreso"


class Sobre(StrEnum):
    """De qué presupuesto sale el gasto."""

    pareja = "pareja"
    familia = "familia"
    personal = "personal"
    iglesia = "iglesia"
    transporte = "transporte"
    ahorro = "ahorro"  # catch-all/discrecional: sale del ahorro (cursos, suscripciones…)


class Categoria(StrEnum):
    comida = "comida"
    hogar = "hogar"
    tecnologia = "tecnologia"
    regalo = "regalo"
    salud = "salud"
    suscripcion = "suscripcion"
    educacion = "educacion"  # cursos, mentorías (inversión)
    transporte = "transporte"
    impuestos = "impuestos"
    entretenimiento = "entretenimiento"
    iglesia = "iglesia"
    otros = "otros"


class FuenteIngreso(StrEnum):
    trabajo = "trabajo"
    proyecto_personal = "proyecto_personal"
    otro = "otro"


class Intent(StrEnum):
    registrar_gasto = "registrar_gasto"
    registrar_ingreso = "registrar_ingreso"
    confirmar = "confirmar"
    cancelar = "cancelar"
    consultar = "consultar"
    otro = "otro"


class GastoDraft(BaseModel):
    """Borrador de gasto extraído del lenguaje natural."""

    monto: float = Field(gt=0)
    sobre: Sobre
    categoria: Categoria
    descripcion: str = Field(min_length=1)
    fecha: date | None = None  # si falta, se asume hoy (confirmable)
    comercio: str | None = None  # Amazon, Shopify, Uber… (recomendado, no obligatorio)


class IngresoDraft(BaseModel):
    """Borrador de ingreso extraído del lenguaje natural."""

    monto: float = Field(gt=0)
    fuente_ingreso: FuenteIngreso
    descripcion: str = Field(min_length=1)
    fecha: date | None = None
    comercio: str | None = None  # cliente/origen (opcional)


class AgentDecision(BaseModel):
    """Salida estructurada del LLM para cada turno."""

    intent: Intent
    gasto: GastoDraft | None = None
    ingreso: IngresoDraft | None = None
    # Campos requeridos que el usuario NO dio (si hay, se pregunta; NO se asume).
    faltan_campos: list[str] = Field(default_factory=list)
    # True cuando hay ambigüedad real (p.ej. salida con pareja Y familia).
    necesita_aclaracion: bool = False
    # Texto natural para responderle al usuario (pregunta/aclaración/charla).
    mensaje: str = ""
