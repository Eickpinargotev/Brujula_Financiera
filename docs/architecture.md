# Arquitectura — Brújula Financiera

## Principio rector

**Single-user, local-first, contenerizado.** Una sola imagen Docker, un solo
contenedor y un dashboard web sobre un núcleo de dominio y una base de datos local.

## Diagrama lógico

```
Navegador ──► web/ (FastAPI + login) ──► domain/ ──► db/ (SQLite)
                                                       │
                                             /data/brujula.db
```

## Un solo proceso

`main.py` crea la app de FastAPI y prepara la base de datos durante el arranque. Así:

- No hay multi-contenedor (encaja con "App" de EasyPanel).
- No hay integraciones externas obligatorias.

## Capas y dependencias

| Capa | Responsabilidad | Puede importar |
|---|---|---|
| `config/` | Settings (env) | — |
| `core/` | Seguridad, logging, utilidades | config |
| `db/` | Engine, modelos, repositorios | config, core |
| `domain/` | **Lógica financiera pura** (sin IO) | (datos planos) |
| `services/` | Reportes y servicios internos | config, core |
| `web/` | Adaptador dashboard | domain, db, core, config |

Regla: **el dominio no depende de nada de infraestructura**. Toda la matemática vive en
`domain/` y es 100 % testeable.

## Datos

- **SQLite** (`aiosqlite` + SQLAlchemy async) en `/data/brujula.db`.
- Al arrancar, `db/bootstrap.py` crea las tablas y **siembra** parámetros, metas y sobres
  (`db/seed.py`). **Todos los datos financieros viven en la BD, nada en `.env`.**
- Respaldo = copiar ese archivo.
- Esquema: ver `docs/finance-model.md` §6 (parameters, goals, envelopes, incomes, expenses).

## Tecnologías

FastAPI · Uvicorn · Jinja2 · SQLAlchemy 2 · aiosqlite · pydantic-settings.
