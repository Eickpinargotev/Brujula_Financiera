"""Capacidades del agente (mapa de referencia).

La "extracción con esquema estricto" se implementa con **salida estructurada** del LLM
(`agent/schemas.py::AgentDecision`), no con tool-calling libre: es más determinístico y
barato. La **persistencia** la hace `db/repository.py::add_movimiento` SOLO tras la
confirmación del usuario. Las **consultas** las calcula `services/reports.py` en Python.

Capacidades por intención (ver `agent/graph.py`):
    registrar_gasto / registrar_ingreso  -> borrador validado + confirmación + persistir
    confirmar / cancelar                 -> aplicar o descartar el borrador pendiente
    consultar                            -> reporte calculado (solo lectura)
    otro                                 -> charla / ayuda
"""

from __future__ import annotations
