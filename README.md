# 🧭 Brújula Financiera

Dashboard financiero personal para registrar ingresos, gastos y transferencias, saber
dónde está tu dinero y seguir tus metas con proyecciones en tiempo real.

> Proyecto **single-user**, **local-first** y **contenerizado**. Nada de tus datos
> financieros sale de tu infraestructura.

---

## ✨ Qué hace

- 💳 **Cuentas y conciliación** para bancos, billeteras y exchanges.
- ↔️ **Transferencias propias** que mueven saldos sin inflar ingresos ni gastos.
- 💰 **Presupuesto por sobres con arrastre** (familia 10 %, relación 10 %, iglesia $60…).
- 🎯 **Metas a contado**: carro eléctrico ($27.000, antes de los 30) y casa ($100.000,
  antes de los 35), con sección **motivadora** ("lo lograrás a los X años, Y meses").
- 📊 **Dashboard privado** con semáforo mensual (🟢/🔴), proyecciones y el simulador
  *"si subo mis ingresos $X, recorto la espera Y"*.

## 🏗️ Arquitectura (resumen)

Una **sola imagen Docker** corre el dashboard FastAPI. La información se guarda en
**SQLite** sobre un volumen `/data`.

```
Navegador ──► Dashboard (FastAPI, login) ──► SQLite (/data)
```

Detalle completo en [`docs/architecture.md`](docs/architecture.md) y las reglas de
desarrollo/despliegue en [`CLAUDE.md`](CLAUDE.md).

## 🚀 Puesta en marcha (todo en Docker)

> ⚠️ **No se ejecuta nada en el host.** Todo el desarrollo y las pruebas se hacen
> dentro del contenedor.

1. Copia el archivo de variables y complétalo:
   ```bash
   cp .env.example .env
   # edita .env con tus credenciales
   ```
2. Levanta el contenedor de desarrollo:
   ```bash
   make up        # o: docker compose up --build
   ```
3. Dashboard en `http://localhost:8000`.

Comandos útiles en el [`Makefile`](Makefile) (`make logs`, `make sh`, `make down`,
`make test`, `make lint`).

## 🔐 Seguridad

- El dashboard pide **una contraseña** y no muestra tu nombre.
- En `.env` solo hay **secretos e infraestructura**; los **parámetros financieros y las
  metas viven en la base de datos** (se siembran al iniciar y se editan en el dashboard).
- Secretos solo en `.env` (ignorado por git). Ver [`CLAUDE.md`](CLAUDE.md) → Seguridad.
- `.gitignore` y `.dockerignore` excluyen bases de datos, respaldos, archivos de
  importación y exportación, conciliaciones en `outputs/` y configuración local.
  Los datos cargados permanecen en `data/`; el repositorio conserva únicamente
  `data/.gitkeep` y la plantilla `.env.example` con credenciales vacías.

## ☁️ Despliegue

Una sola App en **EasyPanel** + volumen persistente. Guía paso a paso en
[`docs/deployment-easypanel.md`](docs/deployment-easypanel.md).

## 📦 Repositorio

```
REPO_URL = https://github.com/Eickpinargotev/Brujula_Financiera.git
```

> Los `commit` los hace el asistente; el `push` **siempre** se confirma antes.

## 📄 Licencia

Uso personal. Privado.
