# 🧭 Brújula Financiera

Copiloto financiero personal: registras ingresos y gastos por **Telegram** (texto o
audio), un agente de IA los confirma y guarda, y un **dashboard** privado te muestra
tu progreso hacia tus metas con proyecciones en tiempo real.

> Proyecto **single-user**, **local-first** y **contenerizado**. Nada de tus datos
> financieros sale de tu infraestructura.

---

## ✨ Qué hace

- 📥 **Captura por Telegram** (voz vía **ElevenLabs Scribe v2**, o texto). Cada
  transcripción responde citando el audio con su **duración y costo en créditos**
  (`⏱ 0:12 · 💳 1.234 créditos`).
- 🤖 **Agente LangGraph + GPT-4o-mini** que extrae monto, categoría, fecha y fuente,
  **pide confirmación** y recién entonces guarda.
- 💰 **Presupuesto por sobres con arrastre** (familia 10 %, relación 10 %, iglesia $60…).
- 🎯 **Metas a contado**: carro eléctrico ($27.000, antes de los 30) y casa ($100.000,
  antes de los 35), con sección **motivadora** ("lo lograrás a los X años, Y meses").
- 📊 **Dashboard privado** con semáforo mensual (🟢/🔴), proyecciones y el simulador
  *"si subo mis ingresos $X, recorto la espera Y"*.

## 🏗️ Arquitectura (resumen)

Una **sola imagen Docker** corre, en un **solo proceso async**, el dashboard (FastAPI)
y el bot de Telegram (polling). Persistencia en **SQLite** sobre un volumen `/data`.

```
Telegram  ──►  Bot (polling)  ──►  Agente LangGraph  ──►  SQLite (/data)
                                          │                   ▲
Navegador ──►  Dashboard (FastAPI, login) ┘───────────────────┘
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
3. Dashboard en `http://localhost:8000` · el bot empieza a escuchar en Telegram.

Comandos útiles en el [`Makefile`](Makefile) (`make logs`, `make sh`, `make down`,
`make test`, `make lint`).

## 🔐 Seguridad

- El bot **solo** atiende a tu `TELEGRAM_ALLOWED_CHAT_ID`.
- El dashboard pide **una contraseña** y no muestra tu nombre.
- En `.env` solo hay **secretos e infraestructura**; los **parámetros financieros y las
  metas viven en la base de datos** (se siembran al iniciar y se editan por Telegram).
- Secretos solo en `.env` (ignorado por git). Ver [`CLAUDE.md`](CLAUDE.md) → Seguridad.

## ☁️ Despliegue

Una sola App en **EasyPanel** + volumen persistente. Guía paso a paso en
[`docs/deployment-easypanel.md`](docs/deployment-easypanel.md).

## 📦 Repositorio

```
# URL del repo (la coloca el dueño):
REPO_URL = <PENDIENTE>
```

> Los `commit` los hace el asistente; el `push` **siempre** se confirma antes.

## 📄 Licencia

Uso personal. Privado.
