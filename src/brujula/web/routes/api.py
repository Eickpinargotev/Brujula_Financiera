"""API JSON del dashboard (protegida por sesión).

El front la consume con fetch y re-renderiza al instante tras cada alta/baja/edición: el
panel refleja los cambios en tiempo real sin recargar la página.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from brujula.db import repository as repo
from brujula.web import overview as overview_mod
from brujula.web.auth import require_api_session
from brujula.web.catalog import CATEGORIAS, FUENTES_INGRESO
from brujula.web.deps import get_session
from brujula.web.schemas import MetaIn, MetaUpdate, MovimientoIn

router = APIRouter(
    prefix="/api",
    include_in_schema=False,
    dependencies=[Depends(require_api_session)],
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _mov_dict(m: object) -> dict[str, object]:
    return {
        "id": m.id,  # type: ignore[attr-defined]
        "tipo": m.tipo,  # type: ignore[attr-defined]
        "fecha": m.fecha.isoformat(),  # type: ignore[attr-defined]
        "monto": round(m.monto, 2),  # type: ignore[attr-defined]
        "descripcion": m.descripcion,  # type: ignore[attr-defined]
        "sobre": m.sobre,  # type: ignore[attr-defined]
        "categoria": m.categoria,  # type: ignore[attr-defined]
        "fuente_ingreso": m.fuente_ingreso,  # type: ignore[attr-defined]
        "comercio": m.comercio,  # type: ignore[attr-defined]
    }


@router.get("/overview")
async def overview(session: SessionDep) -> dict[str, object]:
    """Estado completo del dashboard (KPIs, sobres, serie, metas, predicción, insights)."""
    return await overview_mod.build_overview(session)


@router.get("/catalogos")
async def catalogos(session: SessionDep) -> dict[str, object]:
    """Opciones para los formularios (sobres desde BD, categorías y fuentes)."""
    sobres = await repo.listar_sobres(session)
    return {
        "sobres": [e.nombre for e in sobres],
        "categorias": CATEGORIAS,
        "fuentes_ingreso": FUENTES_INGRESO,
    }


# --- Movimientos --------------------------------------------------------------------


@router.get("/movimientos")
async def listar(
    session: SessionDep,
    tipo: Annotated[str | None, Query(pattern="^(gasto|ingreso)$")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, object]]:
    """Lista de movimientos (más recientes primero)."""
    movs = await repo.listar_movimientos(session, tipo=tipo, limit=limit, offset=offset)
    return [_mov_dict(m) for m in movs]


def _normalizar_mov(payload: MovimientoIn) -> dict[str, object]:
    """Aplica defaults sensatos según el tipo (compartido por crear y editar)."""
    sobre = payload.sobre
    categoria = payload.categoria
    fuente = payload.fuente_ingreso
    if payload.tipo == "gasto":
        sobre = sobre or "ahorro"  # catch-all si no se indica sobre
        categoria = categoria or "otros"
        fuente = None
    else:  # ingreso
        fuente = fuente or "trabajo"
        sobre = None
        categoria = None
    return {
        "tipo": payload.tipo,
        "monto": payload.monto,
        "fecha": payload.fecha,
        "descripcion": payload.descripcion,
        "sobre": sobre,
        "categoria": categoria,
        "fuente_ingreso": fuente,
        "comercio": payload.comercio,
    }


@router.post("/movimientos", status_code=status.HTTP_201_CREATED)
async def crear(payload: MovimientoIn, session: SessionDep) -> dict[str, object]:
    """Crea un movimiento manual. Aplica defaults sensatos según el tipo."""
    mov = await repo.add_movimiento(session, **_normalizar_mov(payload))  # type: ignore[arg-type]
    await session.commit()
    return _mov_dict(mov)


@router.put("/movimientos/{mov_id}")
async def editar(mov_id: int, payload: MovimientoIn, session: SessionDep) -> dict[str, bool]:
    """Edita un movimiento existente (reemplaza sus campos)."""
    ok = await repo.actualizar_movimiento(session, mov_id, _normalizar_mov(payload))
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existe")
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


@router.post("/metas", status_code=status.HTTP_201_CREATED)
async def crear_meta(payload: MetaIn, session: SessionDep) -> dict[str, object]:
    """Crea una meta. Si no se indica prioridad, va al final de la cola."""
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
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Ya existe una meta con ese nombre."
        ) from exc
    return {"id": meta.id}


@router.patch("/metas/{meta_id}")
async def editar_meta(meta_id: int, payload: MetaUpdate, session: SessionDep) -> dict[str, bool]:
    """Edita campos de una meta (parcial). `limpiar_fecha` quita la fecha objetivo."""
    cambios = payload.model_dump(exclude_unset=True, exclude={"limpiar_fecha"})
    if payload.limpiar_fecha:
        cambios["fecha_objetivo"] = None
    if cambios:
        try:
            ok = await repo.actualizar_meta(session, meta_id, cambios)
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Nombre de meta duplicado."
            ) from exc
        if not ok:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existe")
        await session.commit()
    return {"ok": True}


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
