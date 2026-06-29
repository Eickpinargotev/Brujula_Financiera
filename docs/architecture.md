# Arquitectura — Brújula Financiera

## Principio rector

**Single-user, local-first, contenerizado.** Una sola imagen Docker, un solo
contenedor, un solo proceso async que hospeda dos adaptadores de entrada (el bot de
Telegram y el dashboard web) sobre un núcleo de dominio y una base de datos local.

## Diagrama lógico

```
                    ┌──────────────────────────────────────────────┐
   Telegram  ─────► │  bot/ (polling, auth por chat_id)            │
   (voz/texto)      │        │                                      │
                    │        ▼                                      │
                    │  services/transcription (ElevenLabs Scribe v2)│
                    │        │                                      │
                    │        ▼                                      │
                    │  agent/ (LangGraph + GPT-4o-mini)             │
                    │   - extrae monto/categoría/fecha/fuente       │
                    │   - PIDE CONFIRMACIÓN                          │
                    │        │                                      │
   Navegador ─────► │  web/ (FastAPI + login)   │                  │
   (dashboard)      │        │                  │                  │
                    │        ▼                  ▼                  │
                    │  domain/ (cálculo puro)  ───►  db/ (SQLite)   │
                    │   - sobres / metas / forecast                 │
                    └──────────────────────────────────────────────┘
                                         │
                                   /data/brujula.db  (volumen persistente)
```

## Un solo proceso, dos adaptadores

`main.py` crea la app de FastAPI. En el `lifespan` (startup) arranca el bot de Telegram
en **polling** como tarea del mismo event loop; en shutdown lo detiene limpiamente. Así:

- No hay multi-contenedor (encaja con "App" de EasyPanel).
- No hay webhook público (menor superficie de ataque).
- Bot y dashboard comparten la misma conexión a la BD y la misma config.

## Capas y dependencias

| Capa | Responsabilidad | Puede importar |
|---|---|---|
| `config/` | Settings (env) | — |
| `core/` | Seguridad, logging, utilidades | config |
| `db/` | Engine, modelos, repositorios | config, core |
| `domain/` | **Lógica financiera pura** (sin IO) | (datos planos) |
| `services/` | Integraciones externas (ElevenLabs, reportes) | config, core |
| `agent/` | Orquestación LLM (LangGraph, tools) | domain, db, services, config |
| `bot/` | Adaptador Telegram | agent, services, config, core |
| `web/` | Adaptador dashboard | domain, db, core, config |

Regla: **el dominio no depende de nada de infraestructura**. El LLM nunca calcula
dinero; solo extrae datos. Toda la matemática vive en `domain/` y es 100 % testeable.

## Datos

- **SQLite** (`aiosqlite` + SQLAlchemy async) en `/data/brujula.db`.
- Al arrancar, `db/bootstrap.py` crea las tablas y **siembra** parámetros, metas y sobres
  (`db/seed.py`). **Todos los datos financieros viven en la BD, nada en `.env`.**
- Respaldo = copiar ese archivo.
- Esquema: ver `docs/finance-model.md` §6 (parameters, goals, envelopes, incomes, expenses).

## Tecnologías

FastAPI · Uvicorn · Jinja2 · python-telegram-bot · LangGraph · langchain-openai ·
OpenAI (GPT-4o-mini) · ElevenLabs (Scribe v2, batch) · SQLAlchemy 2 · aiosqlite ·
pydantic-settings.
