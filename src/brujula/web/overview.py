"""Composición del read-model del dashboard.

Orquesta `db.repository` (datos) y `domain` (toda la matemática financiera). La capa web
no calcula dinero: solo arma el JSON que consumen las gráficas.

Metas en **cascada por prioridad**: el patrimonio (pool = saldo inicial + ahorro histórico)
llena la meta #1 por completo antes de pasar a la #2, y así. Las fechas se calculan de forma
secuencial. Todo se deriva de los movimientos → el panel se actualiza al instante.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from dateutil.relativedelta import relativedelta
from sqlalchemy.ext.asyncio import AsyncSession

from brujula.db import repository as repo
from brujula.db.models import Goal
from brujula.domain import budget, finance, forecast
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


def _money(n: float) -> str:
    return f"${n:,.0f}"


def _ahorro_promedio(serie: list[dict[str, Any]]) -> float:
    """Promedio de ahorro en los meses con ingreso (ignora meses vacíos)."""
    ahorros = [float(s["ahorro"]) for s in serie if float(s["ingreso"]) > 0]
    return round(sum(ahorros) / len(ahorros), 2) if ahorros else 0.0


def _add(out: list[dict[str, str]], nivel: str, texto: str) -> None:
    out.append({"nivel": nivel, "texto": texto})


def _insights(
    serie: list[dict[str, Any]],
    gasto_mes: float,
    ahorro_mes: float,
    metas: list[dict[str, Any]],
    proxima: dict[str, Any] | None,
) -> list[dict[str, str]]:
    """Pequeños avisos para el Resumen (gasto/ahorro vs. lo habitual, tendencia, meta)."""
    out: list[dict[str, str]] = []
    # Historial = meses anteriores con ingreso (excluye el mes en curso, aún incompleto).
    hist = [s for s in serie[:-1] if float(s["ingreso"]) > 0]
    if hist:
        avg_gasto = sum(float(s["gasto"]) for s in hist) / len(hist)
        avg_ahorro = sum(float(s["ahorro"]) for s in hist) / len(hist)
        if avg_gasto > 0:
            dif = round((gasto_mes - avg_gasto) / avg_gasto * 100)
            if dif > 15:
                _add(out, "warn", f"Gastas {dif}% más que tu promedio ({_money(avg_gasto)}/mes).")
            elif dif < -15:
                _add(out, "ok", f"Gastas {-dif}% menos que tu promedio. 👏")
        if avg_ahorro > 0:
            difa = round((ahorro_mes - avg_ahorro) / avg_ahorro * 100)
            if difa > 10:
                _add(out, "ok", f"Ahorras {difa}% más de lo habitual este mes. 🎉")
            elif difa < -15:
                _add(out, "warn", f"Ahorras {-difa}% menos de lo habitual.")
    # Tendencia mes a mes.
    if len(serie) >= 2:
        prev = float(serie[-2]["ahorro"])
        if prev > 0:
            if ahorro_mes > prev * 1.05:
                _add(out, "info", "Tu ahorro va en aumento respecto al mes pasado. 📈")
            elif ahorro_mes < prev * 0.95:
                _add(out, "info", "Tu ahorro bajó respecto al mes pasado. 📉")
            else:
                _add(out, "info", "Tu ahorro se mantiene estable. ➖")
    # Meta en curso.
    if proxima is not None:
        pct = round(float(proxima["progreso"]) * 100)
        rest = _money(float(proxima["restante"]))
        nombre = f"{proxima['emoji']} {proxima['nombre']}"
        _add(out, "info", f"Meta actual: {nombre} — {pct}% ({rest} restante).")
    elif metas:
        _add(out, "ok", "¡Todas tus metas están cubiertas por tu patrimonio! 🏆")
    return out[:4]


def _target_date(g: Goal, birth: date) -> date | None:
    """Fecha objetivo de una meta: exacta si existe, si no por edad, si no None."""
    if g.fecha_objetivo is not None:
        return g.fecha_objetivo
    if g.edad_objetivo is not None:
        return finance.target_date_for_age(birth, g.edad_objetivo)
    return None


async def build_overview(session: AsyncSession, hoy: date | None = None) -> dict[str, Any]:
    """Devuelve el estado completo del dashboard como diccionario serializable."""
    hoy = hoy or today()
    params = await repo.parametros(session)

    base_salary = _num(params, "base_salary", 1600.0)
    iess = _num(params, "iess_personal_rate", 0.0945)
    itax = _num(params, "income_tax_monthly", 0.0)
    extra_base = _num(params, "extra_income_baseline", 100.0)
    saldo_inicial = _num(params, "saldo_inicial", 0.0)
    currency = params.get("currency", "USD")
    try:
        birth = date.fromisoformat(params.get("birth_date", "1998-01-01"))
    except ValueError:
        birth = date(1998, 1, 1)

    ingreso_baseline = round(finance.net_salary(base_salary, iess, itax) + extra_base, 2)

    anio, mes = hoy.year, hoy.month
    ingreso_mes, gasto_mes = await repo.totales_mes(session, anio, mes)
    ingreso_para_sobres = ingreso_mes if ingreso_mes > 0 else ingreso_baseline

    # --- Sobres + semáforo ---
    sobres = await repo.listar_sobres(session)
    gasto_sobre = await repo.gasto_por_sobre(session, anio, mes)
    asign_no_residual = 0.0
    sobres_out: list[dict[str, Any]] = []
    residual = None
    for e in sobres:
        if e.tipo == "residual":
            residual = e
            continue
        asignado = round(budget.allocation(e.tipo, e.valor, ingreso_para_sobres), 2)
        asign_no_residual += asignado
        gastado = gasto_sobre.get(e.nombre, 0.0)
        sobres_out.append(
            {
                "nombre": e.nombre,
                "tipo": e.tipo,
                "asignado": asignado,
                "gastado": round(gastado, 2),
                "disponible": round(asignado - gastado, 2),
                "estado": budget.semaforo(asignado, gastado),
            }
        )
    if residual is not None:
        asignado = round(budget.residual_allocation(ingreso_para_sobres, asign_no_residual), 2)
        gastado = gasto_sobre.get(residual.nombre, 0.0)
        sobres_out.append(
            {
                "nombre": residual.nombre,
                "tipo": "residual",
                "asignado": asignado,
                "gastado": round(gastado, 2),
                "disponible": round(asignado - gastado, 2),
                "estado": budget.semaforo(asignado, gastado),
            }
        )

    # --- Serie mensual + ahorro promedio + patrimonio (pool) ---
    serie = await repo.serie_mensual(session, meses=HISTORY_MONTHS, hoy=hoy)
    ahorro_prom = _ahorro_promedio(serie)
    profit_total = await repo.total_profit(session)
    pool = round(saldo_inicial + profit_total, 2)

    # --- Distribución por categoría (mes actual) ---
    gasto_cat = await repo.gasto_por_categoria(session, anio, mes)
    categorias = [
        {"nombre": k, "monto": v}
        for k, v in sorted(gasto_cat.items(), key=lambda kv: kv[1], reverse=True)
    ]

    # --- Metas en cascada por prioridad ---
    metas_db = await repo.listar_metas(session)
    asignados, libre = goals_dom.asignar_cascada(pool, [g.monto_objetivo for g in metas_db])
    metas_out: list[dict[str, Any]] = []
    cum = 0.0
    proxima_id: int | None = None
    for i, g in enumerate(metas_db):
        cum += g.monto_objetivo
        ahorrado = asignados[i]
        rest = round(max(g.monto_objetivo - ahorrado, 0.0), 2)
        completada = rest <= 0.005
        target = _target_date(g, birth)
        meses_est = goals_dom.meses_hasta_objetivo(pool, cum, ahorro_prom)
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
        metas_out.append(
            {
                "id": g.id,
                "nombre": g.nombre,
                "emoji": g.emoji or "🎯",
                "monto_objetivo": round(g.monto_objetivo, 2),
                "prioridad": g.prioridad,
                "edad_objetivo": g.edad_objetivo,
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

    ahorro_mes = round(ingreso_mes - gasto_mes, 2)
    tasa = round(ahorro_mes / ingreso_mes, 4) if ingreso_mes > 0 else 0.0

    return {
        "moneda": currency,
        "hoy": hoy.isoformat(),
        "mes_actual": hoy.strftime("%Y-%m"),
        "kpis": {
            "ingreso_mes": ingreso_mes,
            "gasto_mes": gasto_mes,
            "ahorro_mes": ahorro_mes,
            "tasa_ahorro": tasa,
            "ahorro_promedio": ahorro_prom,
            "ingreso_baseline": ingreso_baseline,
            "saldo_estimado": pool,
        },
        "sobres": sobres_out,
        "serie": serie,
        "categorias": categorias,
        "metas": metas_out,
        "prediccion": {
            "pool": pool,
            "profit_total": profit_total,
            "saldo_inicial": round(saldo_inicial, 2),
            "ahorro_promedio": ahorro_prom,
            "libre": libre,
            "proxima": proxima,
            "todo_completado": bool(metas_out) and all(m["completada"] for m in metas_out),
        },
        "proyeccion": proyeccion,
        "insights": _insights(serie, gasto_mes, ahorro_mes, metas_out, proxima),
    }
