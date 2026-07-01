"""Catálogos de la UI (opciones de los formularios). Espejo de docs/finance-model.md §6.

Los sobres se leen de la BD; categorías y fuentes son enumeraciones del modelo.
"""

from __future__ import annotations

CATEGORIAS: list[str] = [
    "comida",
    "hogar",
    "tecnologia",
    "regalo",
    "salud",
    "suscripcion",
    "educacion",
    "transporte",
    "impuestos",
    "entretenimiento",
    "iglesia",
    "otros",
]

FUENTES_INGRESO: list[str] = ["trabajo", "proyecto_personal"]
