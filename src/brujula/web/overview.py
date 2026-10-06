"""Composición del read-model del dashboard.

Orquesta `db.repository` (datos) y `domain` (toda la matemática financiera). La capa web
no calcula dinero: solo arma el JSON que consumen las gráficas.

Metas en **cascada por prioridad**: el patrimonio líquido (pool = dinero en cuentas)
llena la meta #1 por completo antes de pasar a la #2, y así. Las fechas se calculan de forma
secuencial y las manda el **compromiso mensual** de cada meta (fallback: ahorro promedio).
Todo se deriva de los movimientos → el panel se actualiza al instante.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from dateutil.relativedelta import relativedelta
from sqlalchemy.ext.asyncio import AsyncSession

from brujula.db import repository as repo
from brujula.db.models import Goal
from brujula.domain import budget, finance, forecast, loans
from brujula.domain import goals as goals_dom
from brujula.domain.dates import today

HISTORY_MONTHS = 6
PROJECTION_MONTHS = 12


def _num(params: dict[str, str], key: str, default: float) -> float:
    raw = params.get(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _ahorro_promedio(serie: list[dict[str, Any]]) -> float:
    """Promedio de ahorro en los meses con ingreso (ignora meses vacíos)."""
    ahorros = [float(s["ahorro"]) for s in serie if float(s["ingreso"]) > 0]
    return round(sum(ahorros) / len(ahorros), 2) if ahorros else 0.0


def _estado(asignado: float, arrastre: float, gastado: float, con_tope: bool) -> str:
    """Semáforo del sobre: lo gastado en el periodo contra el margen real disponible.

    El margen es `asignado + arrastre`: el arrastre es colchón ("me puedo pasar esto y no
    pasa nada"), por eso cuenta para el color aunque NO se sume al tope que se muestra.
    Si no has gastado nada en el periodo no hay nada que señalar (un arrastre negativo se ve
    en su propia línea, en rojo) — el semáforo habla del periodo, no de la deuda vieja.
    """
    if not con_tope:
        return "libre"
    if gastado <= 0:
        return "verde"
    return budget.semaforo(asignado + arrastre, gastado)


def _asignaciones_del_mes(
    sobres: list[Any], ingreso: float
) -> dict[str, float]:
    """Asignación de cada sobre para UN mes con `ingreso` de ingreso total."""
    out: dict[str, float] = {}
    no_residual = 0.0
    for e in sobres:
        if e.tipo == "residual":
            continue
        asignado = budget.allocation(e.tipo, e.valor, ingreso)
        out[e.nombre] = asignado
        no_residual += asignado
    for e in sobres:
        if e.tipo == "residual":
            out[e.nombre] = budget.residual_allocation(ingreso, no_residual)
    return out


async def _arrastre_por_sobre(
    session: AsyncSession, sobres: list[Any], desde: date
) -> dict[str, float]:
    """Saldo acumulado de cada sobre ANTES del periodo elegido (mes a mes).

    Por cada mes con actividad previo a `desde`: asignado (según el ingreso REAL de ese
    mes) − gastado. La suma es el arrastre: positivo si sobró, negativo si te pasaste.

    El arrastre aplica a TODAS las categorías (la columna `envelopes.arrastre` quedó como
    legado: no se edita en ninguna parte y desactivarla escondería justo este cálculo).
    """
    vacio = {e.nombre: 0.0 for e in sobres}
    inicio = await repo.primera_fecha(session)
    if inicio is None or inicio >= desde:
        return vacio
    fin = desde - relativedelta(days=1)
    ingresos = await repo.ingreso_por_mes(session, inicio, fin)
    gastos = await repo.gasto_por_sobre_por_mes(session, inicio, fin)
    historial: dict[str, list[tuple[float, float]]] = {e.nombre: [] for e in sobres}
    for periodo in sorted(set(ingresos) | set(gastos)):
        asignaciones = _asignaciones_del_mes(sobres, ingresos.get(periodo, 0.0))
        gasto_mes = gastos.get(periodo, {})
        for nombre, asignado in asignaciones.items():
            historial[nombre].append((asignado, gasto_mes.get(nombre, 0.0)))
    return {e.nombre: budget.arrastre(historial[e.nombre]) for e in sobres}


async def _categorias(
    session: AsyncSession, desde: date, hasta: date
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Gasto y asignaciones del rango; arrastre de meses anteriores al primer mes.

    Los topes fijos cuentan una vez por mes calendario incluido, sin prorrateo diario.
    Porcentajes y residual usan los ingresos del rango, calculados mes a mes.
    """
    sobres = [e for e in await repo.listar_sobres(session) if not loans.is_loan_category(e.nombre)]
    gasto_sobre = await repo.gasto_por_sobre_rango(session, desde, hasta)
    inicio_mes = desde.replace(day=1)
    arrastres = await _arrastre_por_sobre(session, sobres, inicio_mes)
    ingresos = await repo.ingreso_por_mes(session, desde, hasta)
    asignaciones = {e.nombre: 0.0 for e in sobres}
    mes = inicio_mes
    while mes <= hasta:
        asignacion_mes = _asignaciones_del_mes(sobres, ingresos.get(mes.strftime("%Y-%m"), 0.0))
        for nombre, asignado in asignacion_mes.items():
            asignaciones[nombre] += asignado
        mes += relativedelta(months=1)
    out: list[dict[str, Any]] = []
    for e in sobres:
        asignado = round(asignaciones[e.nombre], 2)
        con_tope = e.tipo == "residual" or e.valor > 0
        # Una categoría sin tope nunca "sobra" ni "se pasa": no acumula arrastre.
        arr = round(arrastres.get(e.nombre, 0.0), 2) if con_tope else 0.0
        gastado = round(gasto_sobre.get(e.nombre, 0.0), 2)
        out.append(
            {
                "nombre": e.nombre,
                "tipo": e.tipo,
                "asignado": asignado,
                "arrastre": arr,
                "gastado": gastado,
                "disponible": round(asignado - gastado, 2),
                "margen": round(asignado + arr - gastado, 2),
                "estado": _estado(asignado, arr, gastado, con_tope),
            }
        )
    periodo = {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "mes": (
            hasta.strftime("%Y-%m")
            if desde.strftime("%Y-%m") == hasta.strftime("%Y-%m") else None
        ),
        "meses": _meses_en_rango(desde, hasta),
        "arrastre_antes_de": inicio_mes.isoformat(),
    }
    return out, periodo


async def _saldos_prestamos(session: AsyncSession) -> tuple[float, float]:
    """Dinero por cobrar y por pagar, conciliado por persona y FIFO."""
    historial = await repo.todos_movimientos_cronologicos(session)
    return loans.balances(loans.reconcile(historial))


def _target_date(g: Goal, birth: date) -> date | None:
    """Fecha objetivo de una meta: exacta si existe, si no por edad, si no None."""
    if g.fecha_objetivo is not None:
        return g.fecha_objetivo
    if g.edad_objetivo is not None:
        return finance.target_date_for_age(birth, g.edad_objetivo)
    return None


def _fin_de_mes(d: date) -> date:
    fin: date = d.replace(day=1) + relativedelta(months=1, days=-1)
    return fin


def _meses_en_rango(desde: date, hasta: date) -> int:
    """Cuántos meses calendario toca el rango (mínimo 1). Escala los topes fijos."""
    rd = relativedelta(hasta.replace(day=1), desde.replace(day=1))
    meses: int = rd.years * 12 + rd.months + 1
    return max(meses, 1)


async def _periodo_por_defecto(session: AsyncSession, hoy: date) -> tuple[date, date]:
    """Último mes CON DATOS (si no hay movimientos, el mes en curso)."""
    ultimo = await repo.ultima_fecha(session)
    ref = ultimo or hoy
    return ref.replace(day=1), _fin_de_mes(ref)


async def build_overview(
    session: AsyncSession,
    hoy: date | None = None,
    desde: date | None = None,
    hasta: date | None = None,
) -> dict[str, Any]:
    """Estado completo del dashboard para un periodo (por defecto, el último mes con datos)."""
    hoy = hoy or today()
    if desde is None or hasta is None:
        desde, hasta = await _periodo_por_defecto(session, hoy)
    n_meses = _meses_en_rango(desde, hasta)
    un_mes_exacto = (
        n_meses == 1 and desde.day == 1 and hasta == _fin_de_mes(hasta)
    )
    params = await repo.parametros(session)

    base_salary = _num(params, "base_salary", 1600.0)
    iess = _num(params, "iess_personal_rate", 0.0945)
    itax = _num(params, "income_tax_monthly", 0.0)
    extra_base = _num(params, "extra_income_baseline", 100.0)
    currency = params.get("currency", "USD")
    try:
        birth = date.fromisoformat(params.get("birth_date", "1998-01-01"))
    except ValueError:
        birth = date(1998, 1, 1)

    ingreso_baseline = round(finance.net_salary(base_salary, iess, itax) + extra_base, 2)

    # --- Totales del periodo seleccionado ---
    ingreso_mes, gasto_mes = await repo.totales_rango(session, desde, hasta)

    # Categorías y distribución consultan el mismo periodo que los KPIs.
    sobres_out, sobres_periodo = await _categorias(session, desde, hasta)

    # --- Serie mensual (termina en el mes del periodo) + ahorro promedio + patrimonio ---
    gasto_sobre = await repo.gasto_por_sobre_rango(session, desde, hasta)
    serie = await repo.serie_mensual(session, meses=HISTORY_MONTHS, hoy=hasta)
    ahorro_prom = _ahorro_promedio(serie)
    profit_total = await repo.total_profit(session)
    cuentas = await repo.saldos_cuentas(session)
    pool = round(sum(float(c["saldo"]) for c in cuentas), 2)

    # --- Distribución del gasto por sobre (mes actual) ---
    distribucion = [
        {"nombre": k, "monto": v}
        for k, v in sorted(gasto_sobre.items(), key=lambda kv: kv[1], reverse=True)
    ]

    # --- Metas en cascada por prioridad (el compromiso mensual manda la fecha) ---
    metas_db = await repo.listar_metas(session)
    asignados, libre = goals_dom.asignar_cascada(pool, [g.monto_objetivo for g in metas_db])
    etas = goals_dom.eta_cascada(
        pool, [(g.monto_objetivo, g.ahorro_mensual) for g in metas_db], ahorro_prom
    )
    metas_out: list[dict[str, Any]] = []
    cum = 0.0
    proxima_id: int | None = None
    for i, g in enumerate(metas_db):
        cum += g.monto_objetivo
        ahorrado = asignados[i]
        rest = round(max(g.monto_objetivo - ahorrado, 0.0), 2)
        completada = rest <= 0.005
        target = _target_date(g, birth)
        meses_est = etas[i]
        fecha_est = hoy + relativedelta(months=meses_est) if meses_est is not None else None
        edad_est = forecast.edad_en(birth, fecha_est) if fecha_est else None
        ahorro_necesario: float | None = None
        en_camino: bool | None = None
        if target is not None:
            meses_disp = forecast.meses_entre(hoy, target)
            faltante_acum = max(cum - pool, 0.0)
            ahorro_necesario = round(
                faltante_acum / meses_disp if meses_disp > 0 else faltante_acum, 2
            )
            en_camino = fecha_est is not None and fecha_est <= target
        creada = g.creada_en.date() if g.creada_en else None
        meses_desde: int | None = None
        if creada is not None:
            rd = relativedelta(hoy, creada)
            meses_desde = max(rd.years * 12 + rd.months, 0)
        metas_out.append(
            {
                "id": g.id,
                "nombre": g.nombre,
                "emoji": g.emoji or "🎯",
                "monto_objetivo": round(g.monto_objetivo, 2),
                "prioridad": g.prioridad,
                "edad_objetivo": g.edad_objetivo,
                "ahorro_mensual": round(g.ahorro_mensual, 2) if g.ahorro_mensual else None,
                "creada_en": creada.isoformat() if creada else None,
                "meses_desde_creacion": meses_desde,
                "fecha_objetivo_manual": g.fecha_objetivo.isoformat() if g.fecha_objetivo else None,
                "fecha_objetivo": target.isoformat() if target else None,
                "objetivo_acumulado": round(cum, 2),
                "ahorrado": ahorrado,
                "restante": rest,
                "progreso": round(goals_dom.progreso(g.monto_objetivo, ahorrado), 4),
                "completada": completada,
                "meses_estimados": meses_est,
                "fecha_estimada": fecha_est.isoformat() if fecha_est else None,
                "edad_estimada": {"anios": edad_est[0], "meses": edad_est[1]} if edad_est else None,
                "ahorro_necesario": ahorro_necesario,
                "en_camino": en_camino,
                "es_proxima": False,
            }
        )
        if proxima_id is None and not completada:
            proxima_id = g.id
    for m in metas_out:
        m["es_proxima"] = m["id"] == proxima_id
    proxima = next((m for m in metas_out if m["es_proxima"]), None)

    # --- Proyección de patrimonio (línea de predicción) ---
    saldos = forecast.proyeccion_saldo(pool, ahorro_prom, PROJECTION_MONTHS)
    primero = hoy.replace(day=1)
    proyeccion = [
        {"periodo": (primero + relativedelta(months=i)).strftime("%Y-%m"), "saldo": s}
        for i, s in enumerate(saldos)
    ]

    # Balance del periodo = ingresos − gastos (flujo neto). La tasa de ahorro es qué parte
    # del ingreso sobrevivió: balance / ingreso.
    ahorro_mes = round(ingreso_mes - gasto_mes, 2)
    tasa = round(ahorro_mes / ingreso_mes, 4) if ingreso_mes > 0 else 0.0
    prestado, deuda = await _saldos_prestamos(session)

    return {
        "moneda": currency,
        "hoy": hoy.isoformat(),
        "mes_actual": hasta.strftime("%Y-%m"),
        "periodo": {
            "desde": desde.isoformat(),
            "hasta": hasta.isoformat(),
            "meses": n_meses,
            "mes_exacto": un_mes_exacto,
        },
        "kpis": {
            "ingreso_mes": ingreso_mes,
            "gasto_mes": gasto_mes,
            "ahorro_mes": ahorro_mes,
            "tasa_ahorro": tasa,
            "ahorro_promedio": ahorro_prom,
            "ingreso_baseline": ingreso_baseline,
            "saldo_estimado": pool,
            "dinero_cuentas": pool,
            "prestado": prestado,
            "deuda": deuda,
        },
        "sobres": sobres_out,
        "cuentas": {"total": pool, "items": cuentas},
        "sobres_periodo": sobres_periodo,
        "serie": serie,
        "distribucion": distribucion,
        "metas": metas_out,
        "prediccion": {
            "pool": pool,
            "profit_total": profit_total,
            "ahorro_promedio": ahorro_prom,
            "libre": libre,
            "proxima": proxima,
            "todo_completado": bool(metas_out) and all(m["completada"] for m in metas_out),
        },
        "proyeccion": proyeccion,
    }


async def snapshot_meta(
    session: AsyncSession, meta_id: int, hoy: date | None = None
) -> dict[str, Any] | None:
    """Foto actual de UNA meta (ahorrado, meses y fecha estimados) para registrar hitos.

    Usa la misma matemática que el overview: cascada por prioridad y compromiso mensual
    (fallback ahorro promedio). Devuelve None si la meta no existe.
    """
    hoy = hoy or today()
    serie = await repo.serie_mensual(session, meses=HISTORY_MONTHS, hoy=hoy)
    ahorro_prom = _ahorro_promedio(serie)
    pool = await repo.saldo_total_cuentas(session)

    metas_db = await repo.listar_metas(session)
    idx = next((i for i, g in enumerate(metas_db) if g.id == meta_id), None)
    if idx is None:
        return None
    asignados, _ = goals_dom.asignar_cascada(pool, [g.monto_objetivo for g in metas_db])
    etas = goals_dom.eta_cascada(
        pool, [(g.monto_objetivo, g.ahorro_mensual) for g in metas_db], ahorro_prom
    )
    meses = etas[idx]
    return {
        "ahorrado": asignados[idx],
        "meses_estimados": meses,
        "fecha_estimada": hoy + relativedelta(months=meses) if meses is not None else None,
    }
