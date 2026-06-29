"""Herramientas del agente (tool calling con esquema estricto). A completar en desarrollo.

Las tools devuelven/registran datos estructurados; la matemática la hace domain/.
Previstas:
    registrar_gasto(monto, categoria, fecha?, descripcion?)   -> requiere confirmación
    registrar_ingreso(monto, fuente, fecha?, descripcion?)    -> requiere confirmación
    consultar_reporte(periodo)                                -> solo lectura
    estado_metas()                                            -> solo lectura
"""

from __future__ import annotations
