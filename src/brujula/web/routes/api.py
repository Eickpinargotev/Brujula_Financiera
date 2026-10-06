"""API JSON del dashboard (protegida por sesión).

El front la consume con fetch y re-renderiza al instante tras cada alta/baja/edición: el
panel refleja los cambios en tiempo real sin recargar la página.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from brujula.db import repository as repo
from brujula.db.models import Account, Movimiento, Transfer
from brujula.db.versions import record_version
from brujula.domain import loans
from brujula.domain.dates import today
from brujula.web import overview as overview_mod
from brujula.web.auth import require_api_session
from brujula.web.catalog import FUENTES_INGRESO
from brujula.web.deps import get_session
from brujula.web.schemas import (
    CategoriaIn,
    CategoriaUpdate,
    ConciliacionIn,
    CuentaIn,
    CuentaUpdate,
    FuenteIn,
    FuenteUpdate,
    MetaIn,
    MetaUpdate,
    MovimientoIn,
    ParametrosIn,
    TransferenciaIn,
)

router = APIRouter(
    prefix="/api",
    include_in_schema=False,
    dependencies=[Depends(require_api_session)],
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@dataclass
class _LoanAccount:
    person: str
    receivable: float = 0.0
    payable: float = 0.0
    movements: list[dict[str, object]] = field(default_factory=list)
    has_movements_in_range: bool = False


def _mov_dict(
    m: object,
    loan_meta: dict[int, loans.LoanInfo] | None = None,
    account_names: dict[int, str] | None = None,
) -> dict[str, object]:
    out = {
        "version": record_version(cast(Movimiento, m)),
        "id": m.id,  # type: ignore[attr-defined]
        "tipo": m.tipo,  # type: ignore[attr-defined]
        "fecha": m.fecha.isoformat(),  # type: ignore[attr-defined]
        "monto": round(m.monto, 2),  # type: ignore[attr-defined]
        "descripcion": m.descripcion,  # type: ignore[attr-defined]
        "sobre": m.sobre,  # type: ignore[attr-defined]
        # Alias que consume el dashboard: en la UI el sobre se llama "categoría".
        "categoria": m.sobre,  # type: ignore[attr-defined]
        "fuente_ingreso": m.fuente_ingreso,  # type: ignore[attr-defined]
        "comercio": m.comercio,  # type: ignore[attr-defined]
        "account_id": m.account_id,  # type: ignore[attr-defined]
        "cuenta": (account_names or {}).get(m.account_id),  # type: ignore[attr-defined]
    }
    if loan_meta is not None:
        out["prestamo"] = loan_meta.get(m.id)  # type: ignore[attr-defined]
    return out


def _cat_dict(e: object) -> dict[str, object]:
    return {
        "id": e.id,  # type: ignore[attr-defined]
        "nombre": e.nombre,  # type: ignore[attr-defined]
        "tipo": e.tipo,  # type: ignore[attr-defined]
        "valor": round(e.valor, 4),  # type: ignore[attr-defined]
    }


def _validar_rango(desde: date | None, hasta: date | None) -> None:
    """Ambos o ninguno, y en orden. Evita rangos absurdos desde el front."""
    if (desde is None) != (hasta is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Indica 'desde' y 'hasta' juntos.",
        )
    if desde is not None and hasta is not None and desde > hasta:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="'desde' no puede ser posterior a 'hasta'.",
        )


@router.get("/overview")
async def overview(
    session: SessionDep, desde: date | None = None, hasta: date | None = None
) -> dict[str, object]:
    """Estado del dashboard para un periodo. Sin rango: el último mes CON datos."""
    _validar_rango(desde, hasta)
    return await overview_mod.build_overview(session, desde=desde, hasta=hasta)


@router.get("/dias")
async def dias(session: SessionDep) -> dict[str, object]:
    """Días y meses que tienen movimientos: el calendario solo deja marcar estos."""
    filas = await repo.dias_con_datos(session)
    primero_contable = await repo.primera_fecha(session)
    ultimo_contable = await repo.ultima_fecha(session)
    meses: dict[str, int] = {}
    for f, n in filas:
        meses[f.strftime("%Y-%m")] = meses.get(f.strftime("%Y-%m"), 0) + n
    return {
        "dias": [{"fecha": f.isoformat(), "movimientos": n} for f, n in filas],
        "meses": [{"periodo": p, "movimientos": n} for p, n in sorted(meses.items())],
        "primero": filas[0][0].isoformat() if filas else None,
        "ultimo": filas[-1][0].isoformat() if filas else None,
        "primero_contable": primero_contable.isoformat() if primero_contable else None,
        "ultimo_contable": ultimo_contable.isoformat() if ultimo_contable else None,
        "total": sum(n for _, n in filas),
    }


@router.delete("/historial")
async def borrar_historial(
    session: SessionDep, desde: date | None = None, hasta: date | None = None
) -> dict[str, int]:
    """Borra el historial de movimientos del rango; sin rango, TODO. Devuelve cuántos borró."""
    _validar_rango(desde, hasta)
    n = await repo.eliminar_movimientos(session, desde, hasta)
    await session.commit()
    return {"eliminados": n}


@router.get("/catalogos")
async def catalogos(session: SessionDep) -> dict[str, object]:
    """Opciones para los formularios: categorías de gasto y de ingreso, ambas desde BD."""
    nombres = [e.nombre for e in await repo.listar_sobres(session)]
    fuentes = [f.nombre for f in await repo.listar_fuentes(session)]
    cuentas = await repo.listar_cuentas(session, incluir_inactivas=False)
    return {
        "sobres": nombres,  # nombre histórico del modelo
        "categorias": nombres,  # nombre de la UI
        # Si el dueño borró todas, se cae a la enumeración del modelo para no dejar el
        # formulario de ingresos sin opciones.
        "fuentes_ingreso": fuentes or FUENTES_INGRESO,
        "cuentas": [{"id": c.id, "nombre": c.nombre, "moneda": c.moneda} for c in cuentas],
    }


# --- Categorías de gasto (Configuración) --------------------------------------------


@router.get("/categorias")
async def listar_categorias(session: SessionDep) -> list[dict[str, object]]:
    """Categorías de gasto con su tope mensual y cuántos movimientos las usan."""
    out = []
    for e in await repo.listar_sobres(session):
        d = _cat_dict(e)
        d["usos"] = await repo.contar_movimientos_por_sobre(session, e.nombre)
        out.append(d)
    return out


@router.post("/categorias", status_code=status.HTTP_201_CREATED)
async def crear_categoria(payload: CategoriaIn, session: SessionDep) -> dict[str, object]:
    """Crea una categoría de gasto (nombre único)."""
    try:
        env = await repo.crear_sobre(
            session, nombre=payload.nombre, tipo=payload.tipo, valor=payload.valor
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Ya existe una categoría con ese nombre."
        ) from exc
    return _cat_dict(env)


@router.patch("/categorias/{cat_id}")
async def editar_categoria(
    cat_id: int, payload: CategoriaUpdate, session: SessionDep
) -> dict[str, bool]:
    """Edita una categoría. Al renombrarla, arrastra los movimientos que la usaban."""
    env = await repo.obtener_sobre(session, cat_id)
    if env is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existe")
    cambios = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not cambios:
        return {"ok": True}
    nombre_previo = env.nombre
    try:
        await repo.actualizar_sobre(session, cat_id, cambios)
        nuevo = cambios.get("nombre")
        if nuevo and nuevo != nombre_previo:
            await repo.renombrar_sobre_en_movimientos(session, nombre_previo, nuevo)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Nombre de categoría duplicado."
        ) from exc
    return {"ok": True}


@router.delete("/categorias/{cat_id}")
async def borrar_categoria(cat_id: int, session: SessionDep) -> dict[str, bool]:
    """Elimina una categoría. Se bloquea si todavía tiene movimientos asociados."""
    env = await repo.obtener_sobre(session, cat_id)
    if env is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existe")
    usos = await repo.contar_movimientos_por_sobre(session, env.nombre)
    if usos:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La usan {usos} movimiento(s). Reasígnalos antes de borrarla.",
        )
    await repo.eliminar_sobre(session, cat_id)
    await session.commit()
    return {"ok": True}


# --- Categorías de ingreso (Configuración) ------------------------------------------


@router.get("/fuentes")
async def listar_fuentes(session: SessionDep) -> list[dict[str, object]]:
    """Categorías de ingreso con cuántos movimientos las usan."""
    out = []
    for f in await repo.listar_fuentes(session):
        out.append(
            {
                "id": f.id,
                "nombre": f.nombre,
                "usos": await repo.contar_movimientos_por_fuente(session, f.nombre),
            }
        )
    return out


@router.post("/fuentes", status_code=status.HTTP_201_CREATED)
async def crear_fuente(payload: FuenteIn, session: SessionDep) -> dict[str, object]:
    """Crea una categoría de ingreso (nombre único)."""
    try:
        fuente = await repo.crear_fuente(session, nombre=payload.nombre)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una categoría de ingreso con ese nombre.",
        ) from exc
    return {"id": fuente.id, "nombre": fuente.nombre}


@router.patch("/fuentes/{fuente_id}")
async def editar_fuente(
    fuente_id: int, payload: FuenteUpdate, session: SessionDep
) -> dict[str, bool]:
    """Renombra una categoría de ingreso, arrastrando los ingresos que la usaban."""
    fuente = await repo.obtener_fuente(session, fuente_id)
    if fuente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existe")
    cambios = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not cambios:
        return {"ok": True}
    nombre_previo = fuente.nombre
    try:
        await repo.actualizar_fuente(session, fuente_id, cambios)
        nuevo = cambios.get("nombre")
        if nuevo and nuevo != nombre_previo:
            await repo.renombrar_fuente_en_movimientos(session, nombre_previo, nuevo)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nombre de categoría de ingreso duplicado.",
        ) from exc
    return {"ok": True}


@router.delete("/fuentes/{fuente_id}")
async def borrar_fuente(fuente_id: int, session: SessionDep) -> dict[str, bool]:
    """Elimina una categoría de ingreso. Se bloquea si todavía tiene ingresos asociados."""
    fuente = await repo.obtener_fuente(session, fuente_id)
    if fuente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existe")
    usos = await repo.contar_movimientos_por_fuente(session, fuente.nombre)
    if usos:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"La usan {usos} movimiento(s). Reasígnalos antes de borrarla.",
        )
    await repo.eliminar_fuente(session, fuente_id)
    await session.commit()
    return {"ok": True}


# --- Parámetros financieros (Configuración) -----------------------------------------

_PARAM_NUM = ("base_salary", "iess_personal_rate", "income_tax_monthly",
              "extra_income_baseline")


@router.get("/parametros")
async def leer_parametros(session: SessionDep) -> dict[str, object]:
    """Parámetros financieros editables (números como float, resto como texto)."""
    params = await repo.parametros(session)
    out: dict[str, object] = {}
    for k in _PARAM_NUM:
        try:
            out[k] = float(params.get(k, 0) or 0)
        except (TypeError, ValueError):
            out[k] = 0.0
    out["currency"] = params.get("currency", "USD")
    return out


@router.put("/parametros")
async def guardar_parametros(payload: ParametrosIn, session: SessionDep) -> dict[str, bool]:
    """Guarda los parámetros enviados (solo los presentes en el body)."""
    cambios = payload.model_dump(exclude_unset=True, exclude_none=True)
    if cambios:
        await repo.guardar_parametros(session, {k: str(v) for k, v in cambios.items()})
        await session.commit()
    return {"ok": True}


# --- Cuentas ------------------------------------------------------------------------


async def _cuenta_valida(
    session: AsyncSession, account_id: int, *, activa: bool = True
) -> Account:
    account = await repo.obtener_cuenta(session, account_id)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Cuenta inexistente."
        )
    if activa and not account.activa:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La cuenta está inactiva.",
        )
    return account


@router.get("/cuentas")
async def listar_cuentas(session: SessionDep) -> dict[str, object]:
    items = await repo.saldos_cuentas(session)
    for item in items:
        item["usos"] = await repo.contar_usos_cuenta(session, int(item["id"]))
    return {"total": round(sum(float(i["saldo"]) for i in items), 2), "items": items}


@router.post("/cuentas", status_code=status.HTTP_201_CREATED)
async def crear_cuenta(payload: CuentaIn, session: SessionDep) -> dict[str, object]:
    try:
        account = await repo.crear_cuenta(session, nombre=payload.nombre, moneda=payload.moneda)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Ya existe una cuenta con ese nombre."
        ) from None
    return {
        "id": account.id,
        "nombre": account.nombre,
        "moneda": account.moneda,
        "activa": True,
        "saldo": 0.0,
    }


@router.patch("/cuentas/{account_id}")
async def editar_cuenta(
    account_id: int, payload: CuentaUpdate, session: SessionDep
) -> dict[str, bool]:
    cambios = payload.model_dump(exclude_unset=True, exclude_none=True)
    if cambios.get("activa") is False:
        saldo = next(
            (c for c in await repo.saldos_cuentas(session) if c["id"] == account_id), None
        )
        if saldo is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existe")
        if abs(float(saldo["saldo"])) >= 0.005:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Concilia la cuenta a $0.00 antes de desactivarla.",
            )
    try:
        ok = await repo.actualizar_cuenta(session, account_id, cambios)
        if not ok:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existe")
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Ya existe una cuenta con ese nombre."
        ) from None
    return {"ok": True}


@router.post("/cuentas/{account_id}/conciliaciones", status_code=status.HTTP_201_CREATED)
async def conciliar_cuenta(
    account_id: int, payload: ConciliacionIn, session: SessionDep
) -> dict[str, object]:
    await _cuenta_valida(session, account_id, activa=False)
    adjustment = await repo.conciliar_cuenta(
        session,
        account_id=account_id,
        saldo_real=payload.saldo_real,
        fecha=payload.fecha,
        descripcion=payload.descripcion,
    )
    assert adjustment is not None
    await session.commit()
    return {
        "id": adjustment.id,
        "account_id": adjustment.account_id,
        "fecha": adjustment.fecha.isoformat(),
        "monto": round(adjustment.monto, 2),
        "saldo": payload.saldo_real,
        "descripcion": adjustment.descripcion,
    }


@router.get("/cuentas/{account_id}/conciliaciones")
async def listar_conciliaciones(
    account_id: int, session: SessionDep
) -> list[dict[str, object]]:
    await _cuenta_valida(session, account_id, activa=False)
    return [
        {
            "id": a.id,
            "fecha": a.fecha.isoformat(),
            "monto": round(a.monto, 2),
            "descripcion": a.descripcion,
        }
        for a in await repo.listar_ajustes_cuenta(session, account_id)
    ]


async def _validar_transferencia(payload: TransferenciaIn, session: AsyncSession) -> None:
    if payload.source_account_id == payload.destination_account_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="La cuenta de origen y destino deben ser distintas.",
        )
    await _cuenta_valida(session, payload.source_account_id)
    await _cuenta_valida(session, payload.destination_account_id)


def _transfer_dict(t: object, names: dict[int, str]) -> dict[str, object]:
    return {
        "version": record_version(cast(Transfer, t)),
        "id": t.id,  # type: ignore[attr-defined]
        "fecha": t.fecha.isoformat(),  # type: ignore[attr-defined]
        "monto": round(t.monto, 2),  # type: ignore[attr-defined]
        "descripcion": t.descripcion,  # type: ignore[attr-defined]
        "source_account_id": t.source_account_id,  # type: ignore[attr-defined]
        "source_account": names.get(t.source_account_id, ""),  # type: ignore[attr-defined]
        "destination_account_id": t.destination_account_id,  # type: ignore[attr-defined]
        "destination_account": names.get(t.destination_account_id, ""),  # type: ignore[attr-defined]
    }


@router.get("/transferencias")
async def listar_transferencias(
    session: SessionDep,
    desde: date | None = None,
    hasta: date | None = None,
    account_id: int | None = None,
) -> list[dict[str, object]]:
    _validar_rango(desde, hasta)
    names = {a.id: a.nombre for a in await repo.listar_cuentas(session)}
    transfers = await repo.listar_transferencias(
        session, desde=desde, hasta=hasta, account_id=account_id
    )
    return [_transfer_dict(t, names) for t in transfers]


@router.post("/transferencias", status_code=status.HTTP_201_CREATED)
async def crear_transferencia(
    payload: TransferenciaIn, session: SessionDep
) -> dict[str, object]:
    await _validar_transferencia(payload, session)
    transfer = await repo.crear_transferencia(session, **payload.model_dump())
    await session.commit()
    names = {a.id: a.nombre for a in await repo.listar_cuentas(session)}
    return _transfer_dict(transfer, names)


@router.put("/transferencias/{transfer_id}")
async def editar_transferencia(
    transfer_id: int, payload: TransferenciaIn, session: SessionDep, request: Request
) -> dict[str, bool]:
    await _check_version(session, Transfer, transfer_id, request)
    await _validar_transferencia(payload, session)
    ok = await repo.actualizar_transferencia(session, transfer_id, payload.model_dump())
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existe")
    await session.commit()
    return {"ok": True}


@router.delete("/transferencias/{transfer_id}")
async def eliminar_transferencia(transfer_id: int, session: SessionDep) -> dict[str, bool]:
    ok = await repo.eliminar_transferencia(session, transfer_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existe")
    await session.commit()
    return {"ok": True}


async def _check_version(
    session: AsyncSession, model: type[Movimiento] | type[Transfer],
    record_id: int, request: Request,
) -> None:
    expected = request.headers.get("If-Match")
    if not expected:
        return  # compatibilidad con clientes anteriores; el dashboard envía la versión
    record = await session.get(model, record_id)
    if record is None or record_version(cast(Movimiento | Transfer, record)) != expected:
        raise HTTPException(
            409, "Este registro cambió desde que lo abriste. Actualiza antes de volver a editar."
        )


# --- Movimientos --------------------------------------------------------------------


@router.get("/movimientos")
async def listar(
    session: SessionDep,
    tipo: Annotated[str | None, Query(pattern="^(gasto|ingreso)$")] = None,
    categoria: Annotated[str | None, Query(max_length=30)] = None,
    fuente: Annotated[str | None, Query(max_length=30)] = None,
    account_id: Annotated[int | None, Query(ge=1)] = None,
    desde: date | None = None,
    hasta: date | None = None,
    prestamos: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, object]]:
    """Lista de movimientos (recientes primero), filtrable por tipo, categoría y rango.

    `categoria` filtra la categoría de gasto (sobre) y `fuente` la de ingreso; el front
    manda solo la que corresponde al tipo elegido.
    """
    movs = await repo.listar_movimientos(
        session,
        tipo=tipo,
        sobre=categoria,
        fuente=fuente,
        account_id=account_id,
        desde=desde,
        hasta=hasta,
        limit=limit,
        offset=offset,
    )
    historial = await repo.todos_movimientos_cronologicos(session)
    loan_meta = loans.reconcile(historial)
    if prestamos is not None:
        movs = [m for m in movs if (m.id in loan_meta) is prestamos]
    names = {a.id: a.nombre for a in await repo.listar_cuentas(session)}
    return [_mov_dict(m, loan_meta, names) for m in movs]


@router.get("/prestamos")
async def listar_prestamos(
    session: SessionDep, desde: date | None = None, hasta: date | None = None
) -> dict[str, object]:
    """Cuentas de préstamo agrupadas por persona con saldo global e historial del rango."""
    _validar_rango(desde, hasta)
    historial = await repo.todos_movimientos_cronologicos(session)
    loan_meta = loans.reconcile(historial)
    names = {a.id: a.nombre for a in await repo.listar_cuentas(session)}
    accounts: dict[str, _LoanAccount] = {}

    for mov in historial:
        info = loan_meta.get(mov.id)
        if info is None:
            continue
        key = loans.normalize(info["persona"])
        account = accounts.setdefault(key, _LoanAccount(person=info["persona"]))
        saldo = float(info["saldo"])
        if saldo > 0.005:
            if info["direccion"] == "cobrar":
                account.receivable = round(account.receivable + saldo, 2)
            else:
                account.payable = round(account.payable + saldo, 2)

        en_rango = (desde is None or mov.fecha >= desde) and (hasta is None or mov.fecha <= hasta)
        if en_rango:
            account.movements.append(_mov_dict(mov, loan_meta, names))
            account.has_movements_in_range = True

    personas: list[dict[str, object]] = []
    total_receivable = total_payable = 0.0
    for account in accounts.values():
        open_account = account.receivable > 0.005 or account.payable > 0.005
        if not open_account and not account.has_movements_in_range:
            continue
        if account.receivable > 0.005:
            direction, balance = "cobrar", account.receivable
        elif account.payable > 0.005:
            direction, balance = "pagar", account.payable
        else:
            direction, balance = "saldado", 0.0
        account.movements.reverse()
        personas.append(
            {
                "persona": account.person,
                "por_cobrar": account.receivable,
                "por_pagar": account.payable,
                "movimientos": account.movements,
                "direccion": direction,
                "saldo": round(balance, 2),
                "estado": "pendiente" if open_account else "pagado",
            }
        )
        total_receivable += account.receivable
        total_payable += account.payable

    personas.sort(
        key=lambda c: (
            c["estado"] == "pagado",
            -cast(float, c["saldo"]),
            loans.normalize(str(c["persona"])),
        )
    )
    return {
        "personas": personas,
        "por_cobrar": round(total_receivable, 2),
        "por_pagar": round(total_payable, 2),
    }


@router.get("/reporte")
async def reporte(
    session: SessionDep,
    desde: date,
    hasta: date,
    tipo: Annotated[str | None, Query(pattern="^(gasto|ingreso)$")] = None,
) -> Response:
    """Descarga un CSV de los movimientos en el rango (BOM UTF-8 para Excel)."""
    movs = await repo.movimientos_en_rango(session, desde, hasta, tipo)
    buf = io.StringIO()
    buf.write("﻿")  # BOM: Excel abre bien los acentos
    writer = csv.writer(buf)
    names = {a.id: a.nombre for a in await repo.listar_cuentas(session)}
    writer.writerow([
        "Fecha", "Tipo", "Monto", "Detalle", "Categoría", "Fuente",
        "Cuenta origen", "Cuenta destino",
    ])
    rows: list[tuple[date, int, list[str]]] = []
    for m in movs:
        rows.append((m.fecha, m.id, [
            m.fecha.isoformat(), m.tipo, f"{m.monto:.2f}", m.descripcion,
            m.sobre or "", m.fuente_ingreso or "",
            names.get(m.account_id, "") if m.account_id is not None else "", "",
        ]))
    if tipo is None:
        for t in await repo.listar_transferencias(session, desde=desde, hasta=hasta):
            rows.append((t.fecha, t.id, [
                t.fecha.isoformat(), "transferencia", f"{t.monto:.2f}", t.descripcion,
                "", "", names.get(t.source_account_id, ""),
                names.get(t.destination_account_id, ""),
            ]))
    for _, _, row in sorted(rows, key=lambda item: (item[0], item[1])):
        writer.writerow(row)
    nombre = f"brujula_movimientos_{desde.isoformat()}_a_{hasta.isoformat()}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


def _normalizar_mov(payload: MovimientoIn) -> dict[str, object]:
    """Aplica defaults sensatos según el tipo (compartido por crear y editar)."""
    sobre = payload.categoria or payload.sobre
    fuente = payload.fuente_ingreso
    if payload.tipo == "gasto":
        sobre = sobre or "ahorro"  # catch-all si no se indica sobre
        fuente = None
    else:  # ingreso
        fuente = fuente or "trabajo"
        sobre = None
    return {
        "tipo": payload.tipo,
        "monto": payload.monto,
        "fecha": payload.fecha,
        "descripcion": payload.descripcion,
        "sobre": sobre,
        "fuente_ingreso": fuente,
        "comercio": payload.comercio,
        "account_id": payload.account_id,
    }


async def _validar_excedente_prestamo(session: AsyncSession, mov_id: int) -> None:
    """Bloquea un pago que cancela una deuda y ademas abriria saldo inverso."""
    historial = await repo.todos_movimientos_cronologicos(session)
    info = loans.reconcile(historial).get(mov_id)
    if info and info["aplicado"] > 0.005 and info["original"] > 0.005:
        excedente = info["original"]
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"El pago supera la deuda pendiente por ${excedente:.2f}. "
                "Registra el pago exacto y el excedente como otro préstamo."
            ),
        )


@router.post("/movimientos", status_code=status.HTTP_201_CREATED)
async def crear(payload: MovimientoIn, session: SessionDep) -> dict[str, object]:
    """Crea un movimiento manual. Aplica defaults sensatos según el tipo."""
    account = await _cuenta_valida(session, payload.account_id)
    mov = await repo.add_movimiento(session, **_normalizar_mov(payload))  # type: ignore[arg-type]
    await _validar_excedente_prestamo(session, mov.id)
    await session.commit()
    return _mov_dict(mov, account_names={account.id: account.nombre})


@router.put("/movimientos/{mov_id}")
async def editar(
    mov_id: int, payload: MovimientoIn, session: SessionDep, request: Request
) -> dict[str, bool]:
    """Edita un movimiento existente (reemplaza sus campos)."""
    await _check_version(session, Movimiento, mov_id, request)
    await _cuenta_valida(session, payload.account_id)
    ok = await repo.actualizar_movimiento(session, mov_id, _normalizar_mov(payload))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existe")
    await _validar_excedente_prestamo(session, mov_id)
    await session.commit()
    return {"ok": True}


@router.delete("/movimientos/{mov_id}")
async def eliminar(mov_id: int, session: SessionDep) -> dict[str, bool]:
    """Elimina un movimiento por id."""
    ok = await repo.eliminar_movimiento(session, mov_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existe")
    await session.commit()
    return {"ok": True}


# --- Metas (cascada por prioridad) --------------------------------------------------


async def _registrar_hito(session: AsyncSession, meta_id: int, compromiso: float) -> None:
    """Guarda la foto del momento (ahorrado + fecha estimada) al fijar el compromiso."""
    snap = await overview_mod.snapshot_meta(session, meta_id)
    if snap is None:
        return
    await repo.crear_hito(
        session,
        goal_id=meta_id,
        fecha=today(),
        ahorro_mensual=compromiso,
        ahorrado=snap["ahorrado"],
        meses_estimados=snap["meses_estimados"],
        fecha_estimada=snap["fecha_estimada"],
    )


@router.post("/metas", status_code=status.HTTP_201_CREATED)
async def crear_meta(payload: MetaIn, session: SessionDep) -> dict[str, object]:
    """Crea una meta. Si trae compromiso mensual, registra el primer hito del historial."""
    prioridad = payload.prioridad or (await repo.max_prioridad(session)) + 1
    try:
        meta = await repo.crear_meta(
            session,
            nombre=payload.nombre,
            monto_objetivo=payload.monto_objetivo,
            prioridad=prioridad,
            emoji=payload.emoji,
            edad_objetivo=payload.edad_objetivo,
            fecha_objetivo=payload.fecha_objetivo,
            ahorro_mensual=payload.ahorro_mensual,
        )
        if payload.ahorro_mensual is not None:
            await _registrar_hito(session, meta.id, payload.ahorro_mensual)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Ya existe una meta con ese nombre."
        ) from exc
    return {"id": meta.id}


@router.patch("/metas/{meta_id}")
async def editar_meta(meta_id: int, payload: MetaUpdate, session: SessionDep) -> dict[str, bool]:
    """Edita campos de una meta (parcial). Si el compromiso mensual cambia, guarda un hito.

    `limpiar_fecha` quita la fecha objetivo; `limpiar_ahorro`, el compromiso mensual.
    """
    meta = await repo.obtener_meta(session, meta_id)
    if meta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existe")
    compromiso_previo = meta.ahorro_mensual

    cambios = payload.model_dump(exclude_unset=True, exclude={"limpiar_fecha", "limpiar_ahorro"})
    if payload.limpiar_fecha:
        cambios["fecha_objetivo"] = None
    if payload.limpiar_ahorro:
        cambios["ahorro_mensual"] = None
    if cambios:
        try:
            await repo.actualizar_meta(session, meta_id, cambios)
            nuevo = cambios.get("ahorro_mensual", compromiso_previo)
            if nuevo is not None and nuevo != compromiso_previo:
                await _registrar_hito(session, meta_id, nuevo)
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Nombre de meta duplicado."
            ) from exc
    return {"ok": True}


@router.get("/metas/{meta_id}/historial")
async def historial_meta(meta_id: int, session: SessionDep) -> dict[str, object]:
    """Historial de compromisos de una meta: cómo fue cambiando la fecha estimada."""
    meta = await repo.obtener_meta(session, meta_id)
    if meta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existe")
    snap = await overview_mod.snapshot_meta(session, meta_id)
    hitos = await repo.historial_meta(session, meta_id)
    creada = meta.creada_en.date() if meta.creada_en else None
    return {
        "id": meta.id,
        "nombre": meta.nombre,
        "emoji": meta.emoji or "🎯",
        "monto_objetivo": round(meta.monto_objetivo, 2),
        "ahorro_mensual": round(meta.ahorro_mensual, 2) if meta.ahorro_mensual else None,
        "creada_en": creada.isoformat() if creada else None,
        "actual": {
            "ahorrado": snap["ahorrado"] if snap else None,
            "meses_estimados": snap["meses_estimados"] if snap else None,
            "fecha_estimada": (
                snap["fecha_estimada"].isoformat() if snap and snap["fecha_estimada"] else None
            ),
        },
        "hitos": [
            {
                "fecha": h.fecha.isoformat(),
                "ahorro_mensual": round(h.ahorro_mensual, 2),
                "ahorrado": round(h.ahorrado, 2),
                "meses_estimados": h.meses_estimados,
                "fecha_estimada": h.fecha_estimada.isoformat() if h.fecha_estimada else None,
            }
            for h in hitos
        ],
    }


@router.delete("/metas/{meta_id}")
async def borrar_meta(meta_id: int, session: SessionDep) -> dict[str, bool]:
    """Elimina una meta y renumera las prioridades restantes (1..n)."""
    ok = await repo.eliminar_meta(session, meta_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existe")
    for pos, m in enumerate(await repo.listar_metas(session), start=1):
        if m.prioridad != pos:
            await repo.actualizar_meta(session, m.id, {"prioridad": pos})
    await session.commit()
    return {"ok": True}


@router.post("/metas/{meta_id}/mover")
async def mover_meta(
    meta_id: int,
    session: SessionDep,
    hacia: Annotated[Literal["arriba", "abajo"], Query()],
) -> dict[str, bool]:
    """Sube/baja la prioridad de una meta intercambiándola con la vecina."""
    metas = await repo.listar_metas(session)
    ids = [m.id for m in metas]
    if meta_id not in ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existe")
    i = ids.index(meta_id)
    j = i - 1 if hacia == "arriba" else i + 1
    if 0 <= j < len(ids):
        ids[i], ids[j] = ids[j], ids[i]
    # Renumera prioridades 1..n según el nuevo orden (deja la cola limpia).
    for pos, mid in enumerate(ids, start=1):
        await repo.actualizar_meta(session, mid, {"prioridad": pos})
    await session.commit()
    return {"ok": True}
