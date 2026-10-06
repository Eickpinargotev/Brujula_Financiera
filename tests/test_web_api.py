"""Pruebas de la API web (login, sesión, CRUD y reporte) sobre una BD en memoria.

No tocan la BD real: se inyecta un engine SQLite en memoria en los globales de
`brujula.db.engine` y credenciales de prueba vía variables de entorno.
"""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from brujula.config.settings import get_settings
from brujula.db import engine as engine_mod
from brujula.db.engine import create_all
from brujula.db.seed import seed_if_empty
from brujula.web import auth as auth_mod

PASSWORD = "clave-de-prueba"
ACCOUNT_ID = 1


@pytest_asyncio.fixture
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[httpx.AsyncClient]:
    """Cliente HTTP contra la app con BD en memoria y credenciales de prueba."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DASHBOARD_PASSWORD", PASSWORD)
    monkeypatch.setenv("SESSION_SECRET", "secreto-de-prueba")
    get_settings.cache_clear()
    auth_mod._attempts.clear()

    eng = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    await create_all(eng)
    maker = async_sessionmaker(eng, expire_on_commit=False)
    async with maker() as s:
        await seed_if_empty(s)
        await s.commit()
    monkeypatch.setattr(engine_mod, "_engine", eng)
    monkeypatch.setattr(engine_mod, "_sessionmaker", maker)

    from brujula.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    await eng.dispose()
    get_settings.cache_clear()
    auth_mod._attempts.clear()


async def _login(client: httpx.AsyncClient) -> None:
    r = await client.post("/login", data={"password": PASSWORD})
    assert r.status_code == 303


async def test_root_redirige_sin_sesion(client: httpx.AsyncClient) -> None:
    r = await client.get("/")
    assert r.status_code == 303
    assert r.headers["location"] == "/login"
    # Headers de seguridad presentes en todas las respuestas.
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("cache-control") == "no-store"


async def test_api_sin_sesion_devuelve_401(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/overview")).status_code == 401
    assert (await client.get("/api/reporte?desde=2026-01-01&hasta=2026-12-31")).status_code == 401


async def test_login_incorrecto(client: httpx.AsyncClient) -> None:
    r = await client.post("/login", data={"password": "mala"})
    assert r.status_code == 401


async def test_login_rate_limit(client: httpx.AsyncClient) -> None:
    for _ in range(5):
        await client.post("/login", data={"password": "mala"})
    r = await client.post("/login", data={"password": "mala"})
    assert r.status_code == 429


async def test_health_reporta_db(client: httpx.AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["db"] == "ok"


async def test_overview_estructura(client: httpx.AsyncClient) -> None:
    await _login(client)
    r = await client.get("/api/overview")
    assert r.status_code == 200
    data = r.json()
    claves = (
        "kpis", "sobres", "sobres_periodo", "serie", "distribucion", "metas", "prediccion",
        "proyeccion",
    )
    for clave in claves:
        assert clave in data
    assert "categorias" not in data  # el gasto se clasifica solo por sobre
    # Metas sembradas en cascada por prioridad.
    assert [m["prioridad"] for m in data["metas"]] == [1, 2]


async def test_crud_movimiento_y_reporte(client: httpx.AsyncClient) -> None:
    await _login(client)
    payload = {
        "tipo": "gasto",
        "monto": 12.5,
        "fecha": "2026-06-15",
        "descripcion": "Prueba de gasto",
        "account_id": ACCOUNT_ID,
        "sobre": "personal",
    }
    r = await client.post("/api/movimientos", json=payload)
    assert r.status_code == 201
    mov_id = r.json()["id"]

    r = await client.put(f"/api/movimientos/{mov_id}", json={**payload, "monto": 20})
    assert r.status_code == 200

    r = await client.get("/api/reporte", params={"desde": "2026-06-01", "hasta": "2026-06-30"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "Prueba de gasto" in r.text
    assert "20.00" in r.text

    r = await client.delete(f"/api/movimientos/{mov_id}")
    assert r.status_code == 200
    assert (await client.delete(f"/api/movimientos/{mov_id}")).status_code == 404


async def test_edicion_obsoleta_no_sobrescribe(client: httpx.AsyncClient) -> None:
    await _login(client)
    payload = {"tipo": "ingreso", "monto": 10, "fecha": "2026-09-12",
               "descripcion": "Janaina", "fuente_ingreso": "prestamo", "account_id": 1}
    created = (await client.post("/api/movimientos", json=payload)).json()
    url = f"/api/movimientos/{created['id']}"
    headers = {"If-Match": created["version"]}
    updated = await client.put(url, json={**payload, "monto": 20}, headers=headers)
    assert updated.status_code == 200
    stale = await client.put(url, json={**payload, "monto": 30}, headers=headers)
    assert stale.status_code == 409
    rows = (await client.get("/api/movimientos")).json()
    assert rows[0]["monto"] == 20


async def test_file_database_backups_and_failure_block_writes(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    from brujula.db.models import Parameter
    from brujula.web import deps

    path = tmp_path / "real.db"
    eng = create_async_engine(f"sqlite+aiosqlite:///{path}")
    await create_all(eng)
    maker = async_sessionmaker(eng, expire_on_commit=False)
    async with maker() as s:
        await seed_if_empty(s)
        s.add(Parameter(key="database_identity", value="test-identity"))
        await s.commit()
    monkeypatch.setattr(engine_mod, "_engine", eng)
    monkeypatch.setattr(engine_mod, "_sessionmaker", maker)
    try:
        await _login(client)
        payload = {"tipo": "gasto", "monto": 12, "fecha": "2026-09-12",
                   "descripcion": "Prueba", "categoria": "personal", "account_id": 1}
        mismatch = await client.post("/api/movimientos", json=payload,
                                     headers={"X-Brujula-Database": "another-database"})
        assert mismatch.status_code == 409
        created = await client.post("/api/movimientos", json=payload)
        assert created.status_code == 201
        assert created.headers["X-Brujula-Database"] == "test-identity"
        record_id = created.json()["id"]
        assert (await client.delete(f"/api/movimientos/{record_id}")).status_code == 200
        copies = sorted((tmp_path / "backups").glob("*.sqlite"))
        assert len(copies) == 2
        with sqlite3.connect(copies[-1]) as backup:
            assert backup.execute("SELECT monto FROM movimientos").fetchone() == (12,)

        def failed_backup(*args: object) -> None:
            raise OSError("No space left on device")

        monkeypatch.setattr(deps, "backup_database", failed_backup)
        assert (await client.post("/api/movimientos", json=payload)).status_code == 503
        assert (await client.get("/api/movimientos")).json() == []
    finally:
        await eng.dispose()


async def test_cuentas_movimientos_transferencias_y_conciliacion(
    client: httpx.AsyncClient,
) -> None:
    await _login(client)
    accounts = (await client.get("/api/cuentas")).json()
    assert [a["nombre"] for a in accounts["items"]] == [
        "Banco Guayaquil", "Banco Pichincha", "Binance", "UglyCash"
    ]
    assert accounts["total"] == 0.0

    income = {
        "tipo": "ingreso", "monto": 100, "fecha": "2026-09-11",
        "descripcion": "Ingreso", "fuente_ingreso": "trabajo", "account_id": 1,
    }
    expense = {
        "tipo": "gasto", "monto": 20, "fecha": "2026-09-11",
        "descripcion": "Gasto", "categoria": "personal", "account_id": 1,
    }
    assert (await client.post("/api/movimientos", json=income)).status_code == 201
    assert (await client.post("/api/movimientos", json=expense)).status_code == 201
    assert (await client.get("/api/cuentas")).json()["items"][0]["saldo"] == 80.0

    transfer = {
        "source_account_id": 1, "destination_account_id": 3,
        "fecha": "2026-09-11", "monto": 30, "descripcion": "Fondos a Binance",
    }
    created = await client.post("/api/transferencias", json=transfer)
    assert created.status_code == 201
    transfer_id = created.json()["id"]
    balances = (await client.get("/api/cuentas")).json()
    assert [a["saldo"] for a in balances["items"]] == [50.0, 0.0, 30.0, 0.0]
    overview = (await client.get("/api/overview")).json()
    assert overview["cuentas"]["total"] == 80.0
    assert overview["kpis"]["ingreso_mes"] == 100.0
    assert overview["kpis"]["gasto_mes"] == 20.0
    days = (await client.get("/api/dias")).json()
    assert days["dias"] == [{"fecha": "2026-09-11", "movimientos": 3}]
    report = await client.get(
        "/api/reporte", params={"desde": "2026-09-11", "hasta": "2026-09-11"}
    )
    assert "transferencia" in report.text
    assert "Banco Guayaquil" in report.text
    assert "Binance" in report.text

    transfer["monto"] = 10
    updated = await client.put(f"/api/transferencias/{transfer_id}", json=transfer)
    assert updated.status_code == 200
    assert [a["saldo"] for a in (await client.get("/api/cuentas")).json()["items"]] == [
        70.0, 0.0, 10.0, 0.0
    ]
    assert (await client.delete(f"/api/transferencias/{transfer_id}")).status_code == 200

    reconciliation = {
        "saldo_real": 75.25, "fecha": "2026-09-11", "descripcion": "Saldo del banco"
    }
    adjusted = await client.post("/api/cuentas/1/conciliaciones", json=reconciliation)
    assert adjusted.status_code == 201
    assert adjusted.json()["monto"] == -4.75
    assert (await client.get("/api/cuentas")).json()["items"][0]["saldo"] == 75.25


async def test_cuenta_obligatoria_y_validaciones(client: httpx.AsyncClient) -> None:
    await _login(client)
    missing = await client.post("/api/movimientos", json={
        "tipo": "gasto", "monto": 1, "fecha": "2026-09-11",
        "descripcion": "Sin cuenta", "categoria": "personal",
    })
    assert missing.status_code == 422
    same = await client.post("/api/transferencias", json={
        "source_account_id": 1, "destination_account_id": 1,
        "fecha": "2026-09-11", "monto": 1, "descripcion": "Inválida",
    })
    assert same.status_code == 422
    assert (await client.patch("/api/cuentas/2", json={"activa": False})).status_code == 200
    inactive = await client.post("/api/movimientos", json={
        "tipo": "ingreso", "monto": 1, "fecha": "2026-09-11",
        "descripcion": "Cuenta inactiva", "fuente_ingreso": "trabajo", "account_id": 2,
    })
    assert inactive.status_code == 422


async def _gasto(client: httpx.AsyncClient, fecha: str, monto: float, desc: str) -> int:
    r = await client.post(
        "/api/movimientos",
        json={"tipo": "gasto", "monto": monto, "fecha": fecha, "account_id": ACCOUNT_ID,
              "descripcion": desc, "categoria": "personal"},
    )
    assert r.status_code == 201
    return int(r.json()["id"])


async def test_dias_con_datos_y_periodo_por_defecto(client: httpx.AsyncClient) -> None:
    await _login(client)
    # Sin historial: no hay días y el periodo cae en el mes en curso.
    d = (await client.get("/api/dias")).json()
    assert (d["dias"], d["primero"], d["ultimo"], d["total"]) == ([], None, None, 0)
    assert (d["primero_contable"], d["ultimo_contable"]) == (None, None)
    hoy = (await client.get("/api/overview")).json()["hoy"]
    p = (await client.get("/api/overview")).json()["periodo"]
    assert p["desde"] == hoy[:7] + "-01" and p["mes_exacto"] is True

    await _gasto(client, "2026-03-10", 10, "marzo A")
    await _gasto(client, "2026-05-04", 20, "mayo A")
    await _gasto(client, "2026-05-04", 5, "mayo B")
    await _gasto(client, "2026-05-20", 30, "mayo C")

    d = (await client.get("/api/dias")).json()
    assert [(x["fecha"], x["movimientos"]) for x in d["dias"]] == [
        ("2026-03-10", 1), ("2026-05-04", 2), ("2026-05-20", 1)
    ]
    assert d["meses"] == [
        {"periodo": "2026-03", "movimientos": 1}, {"periodo": "2026-05", "movimientos": 3}
    ]
    assert (d["primero"], d["ultimo"], d["total"]) == ("2026-03-10", "2026-05-20", 4)

    # Por defecto: el ÚLTIMO MES CON DATOS (mayo), no el mes en curso.
    data = (await client.get("/api/overview")).json()
    assert data["periodo"] == {
        "desde": "2026-05-01", "hasta": "2026-05-31", "meses": 1, "mes_exacto": True
    }
    assert data["kpis"]["gasto_mes"] == 55.0

    # Un solo día.
    r = await client.get("/api/overview", params={"desde": "2026-05-04", "hasta": "2026-05-04"})
    data = r.json()
    assert data["kpis"]["gasto_mes"] == 25.0
    assert data["periodo"]["mes_exacto"] is False

    # Todo el histórico: rango de varios meses (los topes fijos se escalan).
    r = await client.get("/api/overview", params={"desde": "2026-03-10", "hasta": "2026-05-20"})
    data = r.json()
    assert data["kpis"]["gasto_mes"] == 65.0
    assert data["periodo"]["meses"] == 3

    # Rango inválido → 422 (y desde/hasta van siempre juntos).
    assert (
        await client.get("/api/overview", params={"desde": "2026-05-20", "hasta": "2026-03-10"})
    ).status_code == 422
    assert (await client.get("/api/overview", params={"desde": "2026-05-20"})).status_code == 422


async def test_borrar_historial_por_mes_dia_y_todo(client: httpx.AsyncClient) -> None:
    await _login(client)
    await _gasto(client, "2026-03-10", 10, "marzo A")
    await _gasto(client, "2026-05-04", 20, "mayo A")
    await _gasto(client, "2026-05-20", 30, "mayo B")
    await _gasto(client, "2026-06-01", 40, "junio A")

    # Por día.
    r = await client.delete("/api/historial", params={"desde": "2026-05-04", "hasta": "2026-05-04"})
    assert r.status_code == 200 and r.json() == {"eliminados": 1}

    # Por mes.
    r = await client.delete("/api/historial", params={"desde": "2026-05-01", "hasta": "2026-05-31"})
    assert r.json() == {"eliminados": 1}
    assert (await client.get("/api/dias")).json()["total"] == 2

    # Todo (sin rango). Las categorías y los parámetros sobreviven.
    r = await client.delete("/api/historial")
    assert r.json() == {"eliminados": 2}
    d = (await client.get("/api/dias")).json()
    assert (d["total"], d["dias"]) == (0, [])
    assert len((await client.get("/api/categorias")).json()) > 0
    assert (await client.get("/api/parametros")).json()["currency"] == "USD"


async def test_crud_categorias(client: httpx.AsyncClient) -> None:
    await _login(client)
    # Alta: se normaliza el nombre (minúsculas, espacios colapsados).
    r = await client.post("/api/categorias", json={"nombre": "  Mascotas  "})
    assert r.status_code == 201
    cid = r.json()["id"]
    assert r.json()["nombre"] == "mascotas"

    # Duplicada → 409 controlado.
    assert (
        await client.post("/api/categorias", json={"nombre": "mascotas"})
    ).status_code == 409

    # Aparece en los catálogos que alimentan el formulario.
    cat = (await client.get("/api/catalogos")).json()
    assert "mascotas" in cat["categorias"]

    # Editar el tope mensual.
    r = await client.patch(f"/api/categorias/{cid}", json={"tipo": "fijo", "valor": 40})
    assert r.status_code == 200
    fila = next(c for c in (await client.get("/api/categorias")).json() if c["id"] == cid)
    assert (fila["tipo"], fila["valor"], fila["usos"]) == ("fijo", 40.0, 0)

    # Un movimiento la usa → renombrarla arrastra el movimiento y borrarla se bloquea.
    r = await client.post(
        "/api/movimientos",
        json={
            "tipo": "gasto",
            "monto": 9.99,
            "fecha": "2026-06-10",
                "descripcion": "Croquetas",
                "account_id": ACCOUNT_ID,
            "categoria": "mascotas",
        },
    )
    assert r.status_code == 201
    assert r.json()["categoria"] == "mascotas"

    assert (await client.delete(f"/api/categorias/{cid}")).status_code == 409

    r = await client.patch(f"/api/categorias/{cid}", json={"nombre": "perro"})
    assert r.status_code == 200
    movs = (await client.get("/api/movimientos")).json()
    assert next(m for m in movs if m["descripcion"] == "Croquetas")["categoria"] == "perro"

    # Sin movimientos asociados sí se borra.
    mov_id = next(m for m in movs if m["descripcion"] == "Croquetas")["id"]
    assert (await client.delete(f"/api/movimientos/{mov_id}")).status_code == 200
    assert (await client.delete(f"/api/categorias/{cid}")).status_code == 200
    assert (await client.delete(f"/api/categorias/{cid}")).status_code == 404


async def test_crud_fuentes_ingreso(client: httpx.AsyncClient) -> None:
    await _login(client)
    # Sembradas al arrancar y expuestas en los catálogos del formulario.
    nombres = [f["nombre"] for f in (await client.get("/api/fuentes")).json()]
    assert nombres == ["trabajo", "proyecto_personal", "prestamo"]
    assert (await client.get("/api/catalogos")).json()["fuentes_ingreso"] == nombres

    # Alta con el nombre normalizado.
    r = await client.post("/api/fuentes", json={"nombre": "  Freelance UI  "})
    assert r.status_code == 201
    fid = r.json()["id"]
    assert r.json()["nombre"] == "freelance ui"
    assert "freelance ui" in (await client.get("/api/catalogos")).json()["fuentes_ingreso"]

    # Duplicada → 409 controlado.
    assert (await client.post("/api/fuentes", json={"nombre": "freelance ui"})).status_code == 409

    # Un ingreso la usa → borrarla se bloquea y renombrarla arrastra el movimiento.
    r = await client.post(
        "/api/movimientos",
        json={
            "tipo": "ingreso",
            "monto": 300,
            "fecha": "2026-06-20",
                "descripcion": "Landing page",
                "account_id": ACCOUNT_ID,
            "fuente_ingreso": "freelance ui",
        },
    )
    assert r.status_code == 201
    mov_id = r.json()["id"]
    assert next(f for f in (await client.get("/api/fuentes")).json() if f["id"] == fid)["usos"] == 1

    assert (await client.delete(f"/api/fuentes/{fid}")).status_code == 409

    assert (await client.patch(f"/api/fuentes/{fid}", json={"nombre": "diseño"})).status_code == 200
    movs = (await client.get("/api/movimientos")).json()
    assert next(m for m in movs if m["id"] == mov_id)["fuente_ingreso"] == "diseño"

    # Sin ingresos asociados sí se borra.
    assert (await client.delete(f"/api/movimientos/{mov_id}")).status_code == 200
    assert (await client.delete(f"/api/fuentes/{fid}")).status_code == 200
    assert (await client.delete(f"/api/fuentes/{fid}")).status_code == 404


async def test_filtro_movimientos_por_categoria(client: httpx.AsyncClient) -> None:
    await _login(client)
    await _gasto(client, "2026-06-02", 10, "gasto personal")  # categoría "personal"
    r = await client.post(
        "/api/movimientos",
        json={"tipo": "gasto", "monto": 25, "fecha": "2026-06-03", "account_id": ACCOUNT_ID,
              "descripcion": "regalo", "categoria": "pareja"},
    )
    assert r.status_code == 201
    r = await client.post(
        "/api/movimientos",
        json={"tipo": "ingreso", "monto": 1200, "fecha": "2026-06-01", "account_id": ACCOUNT_ID,
              "descripcion": "sueldo", "fuente_ingreso": "trabajo"},
    )
    assert r.status_code == 201

    def descs(movs: list[dict[str, object]]) -> set[object]:
        return {m["descripcion"] for m in movs}

    todos = (await client.get("/api/movimientos")).json()
    assert descs(todos) == {"gasto personal", "regalo", "sueldo"}

    r = await client.get("/api/movimientos", params={"tipo": "gasto", "categoria": "pareja"})
    assert descs(r.json()) == {"regalo"}

    r = await client.get("/api/movimientos", params={"tipo": "ingreso", "fuente": "trabajo"})
    assert descs(r.json()) == {"sueldo"}

    # Categoría sin movimientos → lista vacía (no error).
    r = await client.get("/api/movimientos", params={"categoria": "iglesia"})
    assert r.status_code == 200 and r.json() == []

    # El filtro de categoría se combina con el rango de fechas.
    r = await client.get(
        "/api/movimientos",
        params={"categoria": "pareja", "desde": "2026-06-01", "hasta": "2026-06-02"},
    )
    assert r.json() == []


async def test_parametros_se_guardan(client: httpx.AsyncClient) -> None:
    await _login(client)
    antes = (await client.get("/api/parametros")).json()
    assert antes["currency"] == "USD"

    r = await client.put("/api/parametros", json={"base_salary": 1800.5})
    assert r.status_code == 200
    despues = (await client.get("/api/parametros")).json()
    assert despues["base_salary"] == 1800.5
    # Lo que no se envía no se toca.
    assert despues["iess_personal_rate"] == antes["iess_personal_rate"]
    # Los parámetros de pronóstico no cambian el dinero real en cuentas.
    assert (await client.get("/api/overview")).json()["cuentas"]["total"] == 0.0

    # Valor fuera de rango → 422, sin escribir nada.
    assert (
        await client.put("/api/parametros", json={"iess_personal_rate": 5})
    ).status_code == 422


async def test_reporte_csv_usa_categoria(client: httpx.AsyncClient) -> None:
    await _login(client)
    r = await client.get("/api/reporte", params={"desde": "2026-01-01", "hasta": "2026-12-31"})
    assert r.status_code == 200
    encabezado = r.text.splitlines()[0]
    assert "Categoría" in encabezado
    assert "Comercio" not in encabezado


async def test_crud_metas(client: httpx.AsyncClient) -> None:
    await _login(client)
    r = await client.post("/api/metas", json={"nombre": "dron", "monto_objetivo": 900})
    assert r.status_code == 201
    mid = r.json()["id"]

    # Duplicado → 409 (error controlado, no 500).
    assert (
        await client.post("/api/metas", json={"nombre": "dron", "monto_objetivo": 1})
    ).status_code == 409

    r = await client.post(f"/api/metas/{mid}/mover", params={"hacia": "arriba"})
    assert r.status_code == 200

    r = await client.patch(f"/api/metas/{mid}", json={"monto_objetivo": 1200})
    assert r.status_code == 200

    r = await client.delete(f"/api/metas/{mid}")
    assert r.status_code == 200
    # Tras borrar, las prioridades quedan renumeradas 1..n.
    data = (await client.get("/api/overview")).json()
    assert [m["prioridad"] for m in data["metas"]] == [1, 2]


async def test_compromiso_mensual_registra_historial(client: httpx.AsyncClient) -> None:
    await _login(client)
    # Sin metas sembradas por delante: la cascada empieza en esta meta (números limpios).
    for m in (await client.get("/api/overview")).json()["metas"]:
        assert (await client.delete(f"/api/metas/{m['id']}")).status_code == 200
    # Crear con compromiso → primer hito.
    r = await client.post(
        "/api/metas",
        json={"nombre": "moto", "monto_objetivo": 6000, "prioridad": 1, "ahorro_mensual": 500},
    )
    assert r.status_code == 201
    mid = r.json()["id"]

    h = (await client.get(f"/api/metas/{mid}/historial")).json()
    assert h["nombre"] == "moto"
    assert h["ahorro_mensual"] == 500
    assert h["creada_en"] is not None
    assert len(h["hitos"]) == 1
    assert h["hitos"][0]["ahorro_mensual"] == 500
    assert h["hitos"][0]["meses_estimados"] == 12  # 6000 / 500, sin ahorro previo

    # Subir el compromiso → segundo hito con MENOS meses (la fecha objetivo baja).
    r = await client.patch(f"/api/metas/{mid}", json={"ahorro_mensual": 1000})
    assert r.status_code == 200
    h = (await client.get(f"/api/metas/{mid}/historial")).json()
    assert len(h["hitos"]) == 2
    assert h["hitos"][1]["meses_estimados"] == 6
    assert h["hitos"][1]["meses_estimados"] < h["hitos"][0]["meses_estimados"]

    # Editar OTRO campo sin tocar el compromiso NO crea hito.
    r = await client.patch(f"/api/metas/{mid}", json={"emoji": "🏍️"})
    assert r.status_code == 200
    h = (await client.get(f"/api/metas/{mid}/historial")).json()
    assert len(h["hitos"]) == 2

    # El overview refleja el compromiso y los meses estimados.
    data = (await client.get("/api/overview")).json()
    meta = next(m for m in data["metas"] if m["id"] == mid)
    assert meta["ahorro_mensual"] == 1000
    assert meta["meses_estimados"] == 6

    # Quitar el compromiso (limpiar_ahorro) → vuelve al ahorro promedio, sin hito nuevo.
    r = await client.patch(f"/api/metas/{mid}", json={"limpiar_ahorro": True})
    assert r.status_code == 200
    h = (await client.get(f"/api/metas/{mid}/historial")).json()
    assert h["ahorro_mensual"] is None
    assert len(h["hitos"]) == 2

    # Al borrar la meta, el historial muere con ella (404).
    assert (await client.delete(f"/api/metas/{mid}")).status_code == 200
    assert (await client.get(f"/api/metas/{mid}/historial")).status_code == 404


async def _mov(
    client: httpx.AsyncClient, tipo: str, monto: float, fecha: str, **extra: object
) -> None:
    payload = {
        "tipo": tipo, "monto": monto, "fecha": fecha, "descripcion": "test",
        "account_id": ACCOUNT_ID, **extra,
    }
    r = await client.post("/api/movimientos", json=payload)
    assert r.status_code == 201, r.text


async def test_arrastre_positivo_entre_meses(client: httpx.AsyncClient) -> None:
    """Junio: 10% de 1000 = 100 asignado, 50 gastado → julio arranca con +50 de arrastre."""
    await _login(client)
    await _mov(client, "ingreso", 1000, "2026-06-05", fuente_ingreso="trabajo")
    await _mov(client, "gasto", 50, "2026-06-20", sobre="familia")
    await _mov(client, "ingreso", 1000, "2026-07-05", fuente_ingreso="trabajo")
    await _mov(client, "gasto", 30, "2026-07-10", sobre="familia")

    data = (await client.get("/api/overview")).json()
    assert data["sobres_periodo"]["mes"] == "2026-07"  # último mes con datos
    familia = next(s for s in data["sobres"] if s["nombre"] == "familia")
    # El tope es el del mes; el arrastre va aparte (margen extra), no se suma al tope.
    assert familia["asignado"] == 100.0
    assert familia["arrastre"] == 50.0
    assert familia["gastado"] == 30.0
    assert familia["disponible"] == 70.0
    assert familia["margen"] == 120.0
    assert familia["estado"] == "verde"


async def test_categorias_siguen_el_periodo(client: httpx.AsyncClient) -> None:
    """Elegir junio recalcula gastos, arrastre y margen aunque haya movimientos en julio."""
    await _login(client)
    await _mov(client, "ingreso", 1000, "2026-06-05", fuente_ingreso="trabajo")
    await _mov(client, "gasto", 50, "2026-06-20", sobre="familia")
    await _mov(client, "ingreso", 1000, "2026-07-05", fuente_ingreso="trabajo")
    await _mov(client, "gasto", 30, "2026-07-10", sobre="familia")

    julio = (await client.get("/api/overview")).json()["sobres"]
    otro = (await client.get("/api/overview?desde=2026-06-01&hasta=2026-06-30")).json()["sobres"]
    familia_julio = next(s for s in julio if s["nombre"] == "familia")
    familia_junio = next(s for s in otro if s["nombre"] == "familia")
    assert (familia_julio["gastado"], familia_julio["arrastre"]) == (30.0, 50.0)
    assert (familia_junio["gastado"], familia_junio["arrastre"], familia_junio["margen"]) == (
        50.0, 0.0, 50.0
    )


async def test_arrastre_negativo_y_semaforo_rojo(client: httpx.AsyncClient) -> None:
    """Gastar de más en junio (115 sobre 100) deja julio con −15 de arrastre."""
    await _login(client)
    await _mov(client, "ingreso", 1000, "2026-06-05", fuente_ingreso="trabajo")
    await _mov(client, "gasto", 115, "2026-06-20", sobre="familia")
    # Julio sin ingresos: 10% de 0 = 0 asignado, así que el sobre queda en −15.
    await _mov(client, "gasto", 10, "2026-07-10", sobre="familia")

    data = (await client.get("/api/overview")).json()
    familia = next(s for s in data["sobres"] if s["nombre"] == "familia")
    assert familia["asignado"] == 0.0
    assert familia["arrastre"] == -15.0
    assert familia["gastado"] == 10.0
    assert familia["margen"] == -25.0
    # Gastó $10 sin tope ni colchón (el arrastre ya venía negativo) → rojo.
    assert familia["estado"] == "rojo"


async def test_arrastre_actua_de_colchon_en_el_semaforo(client: httpx.AsyncClient) -> None:
    """Gastar por encima del tope del mes NO es rojo si el arrastre lo cubre."""
    await _login(client)
    await _mov(client, "ingreso", 1000, "2026-06-05", fuente_ingreso="trabajo")  # familia: 100
    await _mov(client, "gasto", 10, "2026-06-20", sobre="familia")  # sobran 90
    # Julio sin ingresos: tope 0, pero hay 90 de colchón y solo gasta 20.
    await _mov(client, "gasto", 20, "2026-07-10", sobre="familia")

    familia = next(
        s for s in (await client.get("/api/overview")).json()["sobres"]
        if s["nombre"] == "familia"
    )
    assert (familia["asignado"], familia["arrastre"], familia["gastado"]) == (0.0, 90.0, 20.0)
    assert familia["estado"] == "verde"


async def test_sin_gasto_en_el_mes_nunca_es_rojo(client: httpx.AsyncClient) -> None:
    """Arrastre negativo pero cero gastos este mes: verde, y el déficit se ve en `arrastre`."""
    await _login(client)
    await _mov(client, "ingreso", 1000, "2026-06-05", fuente_ingreso="trabajo")
    await _mov(client, "gasto", 115, "2026-06-20", sobre="familia")
    await _mov(client, "gasto", 5, "2026-07-10", sobre="personal")  # julio, otra categoría

    familia = next(
        s for s in (await client.get("/api/overview")).json()["sobres"]
        if s["nombre"] == "familia"
    )
    assert (familia["gastado"], familia["arrastre"]) == (0.0, -15.0)
    assert familia["estado"] == "verde"


async def test_arrastre_en_sobre_de_tope_fijo(client: httpx.AsyncClient) -> None:
    """El arrastre aplica a TODAS las categorías, también a las de tope fijo ($60)."""
    await _login(client)
    await _mov(client, "ingreso", 1000, "2026-06-05", fuente_ingreso="trabajo")
    await _mov(client, "gasto", 10, "2026-06-20", sobre="transporte")

    await _mov(client, "gasto", 5, "2026-07-10", sobre="transporte")
    data = (await client.get("/api/overview")).json()
    transporte = next(s for s in data["sobres"] if s["nombre"] == "transporte")
    assert transporte["asignado"] == 60.0
    assert transporte["arrastre"] == 50.0
    assert transporte["margen"] == 105.0


async def test_prestado_total_suma_todo_el_historico(client: httpx.AsyncClient) -> None:
    """Los cobros se aplican FIFO y actualizan estados y saldos sin borrar historial."""
    await _login(client)
    await _mov(
        client, "gasto", 5, "2026-09-01", sobre="prestamo", descripcion="Billy"
    )
    await _mov(
        client, "gasto", 7, "2026-09-01", sobre="prestamo", descripcion=" Billy "
    )
    await _mov(
        client, "ingreso", 10, "2026-09-02", fuente_ingreso="prestamo", descripcion="billy"
    )

    data = (await client.get("/api/overview")).json()
    assert data["kpis"]["prestado"] == 2.0
    assert data["kpis"]["deuda"] == 0.0
    assert data["kpis"]["ingreso_mes"] == 0.0
    assert data["kpis"]["gasto_mes"] == 0.0
    assert data["kpis"]["ahorro_mes"] == 0.0
    assert data["prediccion"]["profit_total"] == 0.0
    assert data["distribucion"] == []
    assert all(s["nombre"] != "prestamo" for s in data["sobres"])

    movs = (await client.get("/api/movimientos?limit=50")).json()
    loans = [m for m in movs if m["prestamo"]]
    first, second, payment = sorted(loans, key=lambda m: m["id"])
    assert first["prestamo"]["estado"] == "pagado"
    assert first["prestamo"]["saldo"] == 0.0
    assert second["prestamo"]["estado"] == "abonado"
    assert second["prestamo"]["saldo"] == 2.0
    assert payment["prestamo"]["estado"] == "aplicado"
    assert payment["prestamo"]["aplicado"] == 10.0

    # La vista normal excluye préstamos; la vista dedicada los agrupa por persona.
    normales = (await client.get("/api/movimientos?limit=50&prestamos=false")).json()
    assert all(m["prestamo"] is None for m in normales)
    cuentas = (await client.get("/api/prestamos")).json()
    assert cuentas["por_cobrar"] == 2.0
    assert cuentas["por_pagar"] == 0.0
    assert len(cuentas["personas"]) == 1
    billy = cuentas["personas"][0]
    assert billy["persona"] == "Billy"
    assert billy["direccion"] == "cobrar"
    assert billy["saldo"] == 2.0
    assert [m["id"] for m in billy["movimientos"]] == [payment["id"], second["id"], first["id"]]

    # Una cuenta abierta no desaparece solo porque su origen quede fuera del rango.
    futuras = (
        await client.get(
            "/api/prestamos", params={"desde": "2026-10-01", "hasta": "2026-10-31"}
        )
    ).json()
    assert futuras["personas"][0]["saldo"] == 2.0
    assert futuras["personas"][0]["movimientos"] == []


async def test_prestamo_recibido_genera_cuenta_por_pagar(client: httpx.AsyncClient) -> None:
    await _login(client)
    await _mov(
        client, "ingreso", 20, "2026-09-01", fuente_ingreso="prestamo", descripcion="Janaina"
    )
    await _mov(
        client, "gasto", 8, "2026-09-03", sobre="prestamo", descripcion="janaina"
    )

    kpis = (await client.get("/api/overview")).json()["kpis"]
    assert kpis["prestado"] == 0.0
    assert kpis["deuda"] == 12.0


async def test_pago_mayor_a_deuda_se_bloquea(client: httpx.AsyncClient) -> None:
    await _login(client)
    await _mov(client, "gasto", 5, "2026-09-01", sobre="prestamo", descripcion="Billy")
    response = await client.post(
        "/api/movimientos",
        json={
            "tipo": "ingreso",
            "account_id": ACCOUNT_ID,
            "monto": 8,
            "fecha": "2026-09-02",
            "fuente_ingreso": "prestamo",
            "descripcion": "Billy",
        },
    )
    assert response.status_code == 422
    assert "supera la deuda" in response.json()["detail"]
    assert (await client.get("/api/overview")).json()["kpis"]["prestado"] == 5.0


async def test_prestamo_no_define_ultimo_mes_del_resumen(client: httpx.AsyncClient) -> None:
    await _login(client)
    await _mov(
        client, "ingreso", 100, "2026-08-05", fuente_ingreso="trabajo", descripcion="Sueldo"
    )
    await _mov(
        client,
        "ingreso",
        500,
        "2026-09-03",
        fuente_ingreso="prestamo",
        descripcion="Billy",
    )

    data = (await client.get("/api/overview")).json()
    assert data["periodo"]["desde"] == "2026-08-01"
    assert data["kpis"]["ingreso_mes"] == 100.0
    assert data["kpis"]["ahorro_mes"] == 100.0
    dias = (await client.get("/api/dias")).json()
    assert dias["ultimo"] == "2026-09-03"
    assert dias["ultimo_contable"] == "2026-08-05"


@pytest.mark.parametrize(
    ("desde", "hasta", "gasto", "asignado", "arrastre", "tope_fijo", "estado"),
    [
        ("2026-07-10", "2026-07-10", 60.0, 0.0, 50.0, 60.0, "rojo"),
        ("2026-07-05", "2026-07-10", 60.0, 100.0, 50.0, 60.0, "verde"),
        ("2026-07-01", "2026-08-31", 80.0, 120.0, 50.0, 120.0, "verde"),
        ("2026-06-01", "2026-08-31", 130.0, 220.0, 0.0, 180.0, "verde"),
        ("2026-07-11", "2026-07-12", 0.0, 0.0, 50.0, 60.0, "verde"),
    ],
)
async def test_categorias_dia_rango_y_historico(
    client: httpx.AsyncClient, desde: str, hasta: str, gasto: float, asignado: float,
    arrastre: float, tope_fijo: float, estado: str,
) -> None:
    await _login(client)
    await _mov(client, "ingreso", 1000, "2026-06-05", fuente_ingreso="trabajo")
    await _mov(client, "gasto", 50, "2026-06-20", sobre="familia")
    await _mov(client, "ingreso", 1000, "2026-07-05", fuente_ingreso="trabajo")
    await _mov(client, "gasto", 60, "2026-07-10", sobre="familia")
    await _mov(client, "ingreso", 200, "2026-08-05", fuente_ingreso="trabajo")
    await _mov(client, "gasto", 20, "2026-08-20", sobre="familia")
    # Los movimientos posteriores no deben contaminar gastos, topes ni arrastre.
    await _mov(client, "ingreso", 9000, "2026-09-05", fuente_ingreso="trabajo")
    await _mov(client, "gasto", 800, "2026-09-06", sobre="familia")
    response = await client.get(f"/api/overview?desde={desde}&hasta={hasta}")
    assert response.status_code == 200
    data = response.json()
    periodo = data["sobres_periodo"]
    assert (periodo["desde"], periodo["hasta"]) == (desde, hasta)
    assert periodo["arrastre_antes_de"] == desde[:7] + "-01"
    categorias = {s["nombre"]: s for s in data["sobres"]}
    familia = categorias["familia"]
    assert (familia["gastado"], familia["asignado"], familia["arrastre"]) == (
        gasto, asignado, arrastre
    )
    assert familia["margen"] == asignado + arrastre - gasto
    assert familia["estado"] == estado
    assert categorias["transporte"]["asignado"] == tope_fijo
    assert sum(s["gastado"] for s in data["sobres"]) == data["kpis"]["gasto_mes"]
    assert sum(s["monto"] for s in data["distribucion"]) == data["kpis"]["gasto_mes"]
