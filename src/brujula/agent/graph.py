"""Construcción del grafo LangGraph del agente. A completar en desarrollo.

Flujo previsto:
    entrada (texto o transcripción)
      -> extraer (LLM + tools, esquema estricto)
      -> ¿faltan campos? -> preguntar
      -> resumir y PEDIR CONFIRMACIÓN
      -> ¿confirmado? -> persistir (db) ; si no -> corregir
"""

from __future__ import annotations
