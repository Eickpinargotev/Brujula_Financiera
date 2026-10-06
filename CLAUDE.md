# CLAUDE.md — Reglas del proyecto Brújula Financiera

Este archivo es la fuente de verdad para cómo se desarrolla, prueba, asegura y despliega
**Brújula Financiera** (paquete Python: `brujula`). Cualquier agente o persona que trabaje
aquí debe respetarlo.

---

## 0. Visión en una frase

Dashboard financiero **single-user, local-first y contenerizado** para cuentas,
movimientos, presupuestos y proyecciones hacia metas.

---

## 1. Reglas de ORO (no negociables)

1. **Todo corre en Docker.** No se ejecuta ni se prueba nada directamente en el host.
   Desarrollo y pruebas se hacen dentro del contenedor (`docker compose ...` / `make ...`).
2. **Una sola imagen, un solo contenedor, un solo proceso.** El dashboard FastAPI se
   despliega en EasyPanel como una "App".
3. **Los secretos solo viven en `.env`** (ignorado por git). El repo solo contiene
   `.env.example` con claves vacías. Nunca se commitean credenciales.
4. **El `git push` SIEMPRE se confirma con el dueño.** Los `commit` los puede hacer el
   asistente; el `push`, jamás sin aprobación explícita.
5. **Estructura profesional, sin monolitos.** Código por capas y responsabilidades
   (ver §3). Un archivo = una responsabilidad clara.
6. **Datos financieros = blindaje.** Ver §6 (Seguridad). Ante la duda, la opción más
   privada gana.

---

## 2. Entornos

| Entorno | Cómo | Notas |
|---|---|---|
| **development** | `docker compose up` (bind-mount de `./src`, `--reload`) | `.env` con `APP_ENV=development`. BD en `./data/`. |
| **production** | 1 imagen en EasyPanel (App) + volumen `/data` | Variables en el panel de EasyPanel. |

`APP_ENV` (`development` | `production`) controla comportamiento (logs, reload, cookies
secure, etc.). Nunca asumir entorno: leerlo de la config.

---

## 3. Estructura del proyecto

```
src/brujula/
├── main.py            # Entrypoint FastAPI y bootstrap de la base
├── config/            # settings.py (pydantic-settings) — única fuente de config
├── core/              # security (hash/sesiones), logging, utilidades transversales
├── db/                # engine, models (SQLAlchemy), repositories (acceso a datos)
├── domain/            # LÓGICA FINANCIERA pura: budget (sobres), forecast, goals
├── services/          # reportes y servicios internos
└── web/               # Dashboard: app, auth, routes/, templates/, static/
```

**Reglas de capas:**
- `domain/` es **puro** (sin IO ni red): solo cálculo financiero.
- `db/repositories/` es el único lugar que toca la BD. `domain` recibe datos, no los lee.
- `web/` es el adaptador de entrada y no contiene la matemática financiera.

---

## 4. Reglas contables

- Cada ingreso y gasto pertenece obligatoriamente a una cuenta.
- Las transferencias internas no son ingresos ni gastos.
- Una conciliación ajusta el saldo sin alterar los indicadores de flujo.
- Los saldos se calculan en código y se redondean a centavos en los límites de la API.

---

## 5. Estilo de código y calidad

- Python 3.12, tipado con type hints; `ruff` (lint+format) y `mypy`.
- Async de punta a punta (FastAPI, SQLAlchemy async + aiosqlite).
- Docstrings en español permitidos; identificadores en inglés (convención).
- Tests con `pytest` (`tests/`), foco en `domain/` (lógica financiera). **Se corren en
  Docker** (`make test`).
- Sin números mágicos: porcentajes/montos a `config` o `domain`.

---

## 6. Seguridad (datos financieros)

- **Dashboard:** login con **una sola contraseña** (`DASHBOARD_PASSWORD`, comparación
  segura/hash). Cookie de sesión firmada con `SESSION_SECRET`, `HttpOnly`, `SameSite=Strict`,
  `Secure` en producción. Expiración de sesión. Rate-limit en `/login`. Errores genéricos.
- **Sin PII en la UI:** el dashboard no muestra el nombre del dueño ni en `<title>`.
- **HTTPS** lo termina el proxy de EasyPanel/Hostinger.
- **BD** siempre en volumen `/data`, nunca dentro de la imagen. Respaldar con la API
  SQLite `backup`, que incluye el WAL; nunca copiar solo el `.db` en caliente.
- **Logs** sin tokens ni montos sensibles en claro cuando no haga falta.

---

## 7. Docker

- `Dockerfile`: multi-stage, `python:3.12-slim`, usuario **no-root**, instala desde
  `pyproject.toml`, expone `8000`, `CMD` = uvicorn sirviendo `brujula.main:app`.
- `docker-compose.yml`: servicio único `brujula`, `env_file: .env`, volúmenes
  `./src:/app/src` (dev reload) y `./data:/data` (BD), puerto `8000:8000`.
- La BD por defecto: `sqlite+aiosqlite:////data/brujula.db`.

---

## 8. Git / commits

- Ramas: trabajar en `feature/*` o `dev`, no directamente en la rama por defecto para
  cambios grandes.
- Mensajes de commit claros y en imperativo.
- **`push` solo tras confirmación del dueño.** URL del repo: ver `.env`/README (pendiente).

---

## 9. Variables de entorno y dónde viven los datos

- **`.env` = SOLO secretos e infraestructura FIJA** (contraseña/secreto del dashboard,
  `DATABASE_URL`, `APP_ENV`). **Nada que varíe.**
- **Los parámetros financieros y las metas NO van en `.env`.** Viven en la **base de
  datos** (tablas `parameters`, `goals`, `envelopes`), se **siembran** al iniciar
  (`db/seed.py`) y se consultan/editan en tiempo de ejecución desde el dashboard.
- Ninguna variable nueva debe leerse fuera de `config/settings.py`.

---

## 10. Estado del proyecto

- [x] Bases / scaffolding (estructura, Docker, docs, config, env)
- [x] Capa de datos (modelos + engine + siembra inicial; bootstrap en el arranque)
- [x] Lógica financiera (`domain/budget`, `goals`, `forecast`: semáforo, metas, proyección y simulador). Incluye el **semáforo acumulado con arrastre** por categoría (`budget.arrastre`).
- [x] Dashboard + login + gráficos (FastAPI + Jinja2 + CSS propio + ECharts vendorizado; login con sesión firmada y rate-limit; API JSON con CRUD manual y refresco en tiempo real). Datos de ejemplo: `db/seed_demo.py` (solo desarrollo).
  - **Vistas: Resumen · Movimientos · Reportes (CSV).** Metas y Predicciones se quitaron
    de la UI por decisión del dueño (29/07/2026); la matemática y la API de metas siguen
    en el código para el bot.
  - **Tema oscuro neutro** (grafito + acento cálido), sin glass ni neón.
  - En la UI el sobre se llama **categoría**: mismo dato (`movimientos.sobre` /
    tabla `envelopes`), nombre más simple. **No se pide comercio** en el formulario.
  - **Categorías de los dos lados del flujo, ambas en BD y editables:** egresos en
    `envelopes` (nombre + tope mensual) e ingresos en `income_sources` (solo nombre; el
    ingreso no se presupuesta). El dato del ingreso sigue siendo `fuente_ingreso`. Ambas
    se crean al vuelo con el ＋ del formulario y se administran en Configuración.
  - **Filtro en Movimientos:** tipo (Todos · Ingresos · Gastos) + un select con las
    categorías del tipo elegido. El valor lleva el tipo dentro (`gasto:pareja`,
    `ingreso:trabajo`) porque un egreso y un ingreso pueden llamarse igual; la API expone
    `GET /api/movimientos?tipo=&categoria=&fuente=`.
  - **Configuración** = ventana flotante (panel izquierdo + detalle + Guardar) con
    Categorías (Egresos/Ingresos: CRUD + tope mensual en egresos), Historial (borrado por
    mes / por día / todo),
    General (preferencias en `localStorage`) y Cuenta. Los parámetros financieros
    (`parameters`) ya **no** se editan en la UI; la API `/api/parametros` sigue viva.
  - **Resumen por periodo:** arranca en el **último mes CON datos** (no el mes en curso) y
    admite último día, todo el histórico o rango personalizado. El calendario deja marcar
    **cualquier día entre el primer movimiento y hoy**; los que tienen movimientos llevan
    un punto (`GET /api/dias`). Los topes fijos se escalan por el nº de meses del rango.
  - **Categorías sigue el rango elegido en Resumen**. Gastado usa solo las fechas
    seleccionadas; asignaciones se suman mes a mes con los ingresos del rango y un
    tope fijo por cada mes calendario incluido (sin prorrateo diario). El arrastre
    comprende los meses anteriores al primer mes seleccionado y va en línea aparte:
    **no se suma al tope**, solo actúa como colchón para el semáforo. Sin gasto en el
    periodo nunca hay rojo. La cabecera muestra el rango y el corte del arrastre.
    Ver `docs/finance-model.md` §2. `envelopes.arrastre` permanece como legado.
  - **Presets del periodo:** Mes pasado · Último mes · Todo · Personalizado (en ese orden).
  - **KPIs:** Ingreso · Gasto · **Balance** (ingreso − gasto, con `prestado` histórico como
    nota) · Tasa de ahorro (balance / ingreso). La tarjeta de Insights se quitó (29/07/2026).
  - **Movimientos y Reportes** usan los mismos presets de datos: Último mes · Todo ·
    Personalizado (Reportes conserva además "Últimos 3 meses").
  - `static_v` (cache-busting de CSS/JS): en producción es el sello del arranque; en
    desarrollo es el mtime más reciente de `web/static/`, para que editar CSS/JS se vea
    al recargar sin reiniciar el contenedor.
- [x] Pruebas en Docker — 80 tests: dominio y API web (sesión, cuentas, conciliaciones,
  transferencias, movimientos, filtros, reporte, préstamos, metas y arrastre por categoría).
- [ ] Despliegue EasyPanel
