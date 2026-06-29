"""Estado del agente.

El estado del grafo (`AgentState`) está definido en `agent/graph.py` junto al grafo que
lo usa: mensajes (con ventana de 7 interacciones), `pending` (borrador a confirmar),
`decision` (salida del LLM del turno) y `reply` (respuesta a enviar).
"""

from __future__ import annotations

from brujula.agent.graph import AgentState

__all__ = ["AgentState"]
