# CLAUDE.md — Reglas del proyecto Brújula Financiera

Este archivo es la fuente de verdad para cómo se desarrolla, prueba, asegura y despliega
**Brújula Financiera** (paquete Python: `brujula`). Cualquier agente o persona que trabaje
aquí debe respetarlo.

---

## 0. Visión en una frase

Copiloto financiero **single-user, local-first y contenerizado**: captura por Telegram
(voz/texto) → agente IA con confirmación → SQLite → dashboard privado con proyecciones
hacia metas.

---

## 1. Reglas de ORO (no negociables)

1. **Todo corre en Docker.** No se ejecuta ni se prueba nada directamente en el host.
   Desarrollo y pruebas se hacen dentro del contenedor (`docker compose ...` / `make ...`).
2. **Una sola imagen, un solo contenedor, un solo proceso.** Dashboard (FastAPI) y bot
   (polling) viven en el mismo event loop async. No multi-servicio. Es lo desplegable
   en EasyPanel como una "App".
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
| **production** | 1 imagen en EasyPanel (App) + volumen `/data` | Variables en el panel de EasyPanel. Polling de Telegram. |

`APP_ENV` (`development` | `production`) controla comportamiento (logs, reload, cookies
secure, etc.). Nunca asumir entorno: leerlo de la config.

---

## 3. Estructura del proyecto

```
src/brujula/
├── main.py            # Entrypoint: arma FastAPI + arranca el bot en el lifespan
├── config/            # settings.py (pydantic-settings) — única fuente de config
├── core/              # security (hash/sesiones), logging, utilidades transversales
├── db/                # engine, models (SQLAlchemy), repositories (acceso a datos)
├── domain/            # LÓGICA FINANCIERA pura: budget (sobres), forecast, goals
├── services/          # integraciones: transcription (ElevenLabs), reports
├── agent/             # LangGraph: graph, state, tools, prompts/ (versionados)
├── bot/               # Telegram: telegram_bot, handlers (auth por chat_id)
└── web/               # Dashboard: app, auth, routes/, templates/, static/
```

**Reglas de capas:**
- `domain/` es **puro** (sin IO, sin red, sin Telegram): solo cálculo financiero. Es lo
  más testeable y donde vive la matemática. El LLM NUNCA calcula saldos; lo hace `domain`.
- `db/repositories/` es el único lugar que toca la BD. `domain` recibe datos, no los lee.
- `agent/` orquesta; delega cálculo en `domain` y persistencia en `db`.
- `bot/` y `web/` son adaptadores de entrada; no contienen lógica financiera.

---

## 4. Reglas para el AGENTE (LangGraph) — evitar prompt overfitting

1. **El LLM solo extrae e interpreta lenguaje natural; no calcula dinero.** Monto,
   categoría, fecha, fuente y descripción se obtienen vía **tool calling con esquema
   estricto** (Pydantic). Saldos/proyecciones → `domain/` en Python.
2. **Prompt general y basado en principios**, no memorización de casos. Pocos ejemplos
   (few-shot mínimos) y **marcados como ilustrativos**, nunca como reglas rígidas.
3. **Confirmación obligatoria antes de escribir.** El agente resume lo que entendió
   ("Esto voy a registrar: $53,90 — salida con pareja — 28/06") y espera tu "sí".
4. **Campos faltantes → preguntar**, no inventar. Si el audio no dice la fecha, asume
   hoy pero permite corrección; si falta el monto, lo pide.
5. **Normalización en código:** montos, monedas y fechas se validan/normalizan en Python
   (no confiar en el formato del LLM). Zona horaria `America/Guayaquil`.
6. **Prompts versionados** en `agent/prompts/*.md`, pequeños y componibles. Cambios de
   prompt se revisan como código.
7. **Determinismo donde importa:** temperatura baja para extracción; las herramientas
   devuelven datos estructurados, no texto libre, cuando alimentan la BD.
8. **Trazabilidad:** registrar (sin secretos) las decisiones del agente para depurar.
9. **Fuentes de ingreso** reconocidas: `trabajo`, `proyecto_personal`. Categorías de
   gasto configurables (ver `docs/finance-model.md`).
10. **Transcripción:** ElevenLabs **Scribe v2** (`scribe_v2`), endpoint batch
    `POST /v1/speech-to-text` (NO realtime ni webhook). Tras transcribir, la respuesta de
    Telegram cita el audio y anexa la línea de uso `⏱ <duración> · 💳 <créditos>`
    (`services/usage.py`). La duración sale de `audio_duration_secs`; el costo, de los
    headers (nombre aún por confirmar → se loguea en DEBUG; fallback "n/d").
11. **Metas a contado**, derivadas de `BIRTH_DATE + edad` (carro 30, casa 35). La sección
    motivadora expresa la fecha proyectada como edad ("a los X años, Y meses").
12. **Guardián determinístico:** la extracción usa **salida estructurada** validada por
    Pydantic (`agent/schemas.py::AgentDecision`). Si un campo requerido falta o es inválido,
    NO se guarda: se pregunta. El LLM nunca calcula dinero ni inventa datos.
13. **Modelo de 3 dimensiones** en cada gasto: `sobre` (presupuesto) · `categoria` (tipo) ·
    `comercio` (a quién). Ingresos llevan `fuente_ingreso`. **No** se registra método de
    pago (siempre tarjeta).
14. **Memoria acotada:** el agente recuerda solo las **últimas 7 interacciones**
    (`agent/memory.py`); la memoria por chat se poda para no crecer ni quemar tokens.
15. **Reintentos acotados** (`agent/llm.py`): ante fallo de formato del LLM, pocos
    reintentos y luego degradación segura (pide repetir), sin loops que quemen tokens.

---

## 5. Estilo de código y calidad

- Python 3.12, tipado con type hints; `ruff` (lint+format) y `mypy`.
- Async de punta a punta (FastAPI, PTB, SQLAlchemy async + aiosqlite).
- Docstrings en español permitidos; identificadores en inglés (convención).
- Tests con `pytest` (`tests/`), foco en `domain/` (lógica financiera). **Se corren en
  Docker** (`make test`).
- Sin números mágicos: porcentajes/montos a `config` o `domain`.

---

## 6. Seguridad (datos financieros)

- **Bot:** solo procesa updates cuyo `chat_id == TELEGRAM_ALLOWED_CHAT_ID`. Lo demás se
  descarta en silencio (no responder a desconocidos).
- **Dashboard:** login con **una sola contraseña** (`DASHBOARD_PASSWORD`, comparación
  segura/hash). Cookie de sesión firmada con `SESSION_SECRET`, `HttpOnly`, `SameSite=Strict`,
  `Secure` en producción. Expiración de sesión. Rate-limit en `/login`. Errores genéricos.
- **Sin PII en la UI:** el dashboard no muestra el nombre del dueño ni en `<title>`.
- **Polling, no webhook:** menos superficie pública.
- **HTTPS** lo termina el proxy de EasyPanel/Hostinger.
- **BD** siempre en volumen `/data`, nunca dentro de la imagen. Respaldo = copiar el
  archivo `.db`.
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

- **`.env` = SOLO infraestructura y secretos** (tokens, claves API, contraseña/secreto del
  dashboard, `DATABASE_URL`, `APP_ENV`, ids de modelos). Documentadas en `.env.example`
  con valores vacíos; el dueño las completa.
- **Los parámetros financieros y las metas NO van en `.env`.** Viven en la **base de
  datos** (tablas `parameters`, `goals`, `envelopes`), se **siembran** al iniciar
  (`db/seed.py`) y se consultan/editan en tiempo de ejecución por Telegram o el dashboard.
- Ninguna variable nueva debe leerse fuera de `config/settings.py`.

---

## 10. Estado del proyecto

- [x] Bases / scaffolding (estructura, Docker, docs, config, env)
- [x] Capa de datos (modelos + engine + siembra inicial; bootstrap en el arranque)
- [x] Transcripción ElevenLabs Scribe v2 (servicio + línea de costo)
- [x] Agente LangGraph (guardián, confirmación, memoria 7 interacciones, consultas)
- [ ] Lógica financiera (`domain/`: sobres acumulados, forecast, motivador) — base en `domain/finance.py`
- [ ] Bot de Telegram (auth, voz, confirmación) — cablear el agente al polling
- [ ] Dashboard + login + gráficos
- [ ] Pruebas en Docker (smoke, finance, usage, transcription, db_seed, agent_*)
- [ ] Despliegue EasyPanel
