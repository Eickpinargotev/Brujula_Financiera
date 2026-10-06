"""Catálogos de la UI (opciones de los formularios). Espejo de docs/finance-model.md §6.

Los sobres se leen de la BD (única clasificación del gasto); las fuentes de ingreso son
una enumeración del modelo.
"""

from __future__ import annotations

FUENTES_INGRESO: list[str] = ["trabajo", "proyecto_personal"]
