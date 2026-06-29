# Despliegue en EasyPanel — Brújula Financiera

Brújula Financiera se despliega como **una sola App** (un contenedor) en EasyPanel, detrás
del proxy con HTTPS, con un **volumen persistente** para la base de datos.

## Requisitos

- VPS con EasyPanel instalado.
- Dominio/subdominio (Hostinger) apuntando al VPS.
- Repositorio en GitHub (build desde el repo) **o** imagen publicada en un registry.

## Pasos

1. **Crear App** en EasyPanel → tipo *App* (no Compose).
2. **Fuente**: conectar el repo de GitHub (build con el `Dockerfile` del proyecto) o
   indicar la imagen `brujula:latest` de un registry.
   - Si se construye en EasyPanel, **no** pasar `INSTALL_DEV` (queda en `false` → imagen
     de producción sin herramientas de dev).
3. **Puerto**: exponer `8000` (el proxy de EasyPanel le pone HTTPS y el dominio).
4. **Volumen persistente**: montar uno en `/data` (ahí vive `brujula.db`).
5. **Variables de entorno** (en el panel, NO en el repo):
   ```
   APP_ENV=production
   TIMEZONE=America/Guayaquil
   TELEGRAM_BOT_TOKEN=...
   TELEGRAM_ALLOWED_CHAT_ID=...
   OPENAI_API_KEY=...
   ELEVENLABS_API_KEY=...
   DASHBOARD_PASSWORD=...
   SESSION_SECRET=...            # openssl rand -hex 32
   DATABASE_URL=sqlite+aiosqlite:////data/brujula.db
   ```
   > `APP_ENV=production` es lo que **activa el polling del bot**. Los ids de modelos son
   > defaults en código (no van en el entorno). Los parámetros financieros viven en la BD.
6. **Dominio**: asignar el subdominio de Hostinger y activar HTTPS (Let's Encrypt).
7. **Deploy** y revisar logs: el dashboard responde y el bot conecta por polling.

## Notas de seguridad en producción

- `APP_ENV=production` activa cookies `Secure` y desactiva el reload.
- El bot solo atiende a `TELEGRAM_ALLOWED_CHAT_ID`.
- El dashboard no muestra el nombre del dueño aunque la URL lo tenga.
- **Polling** (sin webhook): no se expone ningún endpoint de Telegram.

## Respaldos

La BD es un solo archivo: `/data/brujula.db`. Programar copia periódica del volumen
(o `docker cp` / snapshot del volumen en EasyPanel).

## Diferencias dev ↔ prod

| | Desarrollo | Producción |
|---|---|---|
| Orquestación | `docker compose up` | EasyPanel App |
| Código | bind-mount `./src` + `--reload` | copiado en la imagen |
| Dev tools | sí (`INSTALL_DEV=true`) | no |
| Cookies | no-secure | `Secure` |
| BD | `./data/brujula.db` | volumen `/data` |
