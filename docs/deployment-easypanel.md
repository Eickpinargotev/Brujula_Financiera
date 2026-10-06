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
   DASHBOARD_PASSWORD=...
   SESSION_SECRET=...            # openssl rand -hex 32
   DATABASE_URL=sqlite+aiosqlite:////data/brujula.db
   ```
   > Los parámetros financieros viven en la base de datos.
6. **Dominio**: asignar el subdominio de Hostinger y activar HTTPS (Let's Encrypt).
7. **Deploy** y revisar logs: el dashboard y `/health` responden correctamente.

## Notas de seguridad en producción

- `APP_ENV=production` activa cookies `Secure` y desactiva el reload.
- El dashboard no muestra el nombre del dueño aunque la URL lo tenga.

## Respaldos

La única base activa es `/data/brujula.db`. Los archivos `-wal` y `-shm` pertenecen a
esa misma base; no se borran ni se sustituyen mientras la aplicación está en marcha.
La aplicación crea respaldos consistentes con la API SQLite (incluyen el WAL) en
`/data/backups` antes de cada escritura de la API y antes de las migraciones de arranque.
Si el respaldo falla, la escritura se bloquea. No hay borrado automático de respaldos:
vigilar el espacio y copiar periódicamente los archivos terminados a otro dispositivo.
Un respaldo en el mismo disco permite recuperar errores de edición, pero no protege
frente a la pérdida del disco completo.

No copiar únicamente el `.db` en caliente: puede omitir transacciones del WAL.
Para recuperar, detener la aplicación, conservar el conjunto actual `.db`/`-wal`/`-shm`
como evidencia y restaurar un respaldo verificado, sin mezclar su WAL con otro archivo.
Nunca fusionar respaldos por ID: los identificadores pueden haberse reutilizado.

El arranque normal exige que exista una base de Brújula íntegra. Si falta el volumen,
se detiene en vez de crear datos nuevos. Para una instalación deliberadamente vacía,
ejecutar una sola inicialización con `ALLOW_DATABASE_CREATE=true` y volver a `false`.
No habilitarlo para recuperar una base perdida. El arranque no inserta movimientos demo.

Desarrollo y un futuro servidor remoto tendrían discos distintos: no alternar entre
ambos como si se sincronizaran. Elegir un único servidor para registrar las finanzas.

## Diferencias dev ↔ prod

| | Desarrollo | Producción |
|---|---|---|
| Orquestación | `docker compose up` | EasyPanel App |
| Código | bind-mount `./src` + `--reload` | copiado en la imagen |
| Dev tools | sí (`INSTALL_DEV=true`) | no |
| Cookies | no-secure | `Secure` |
| BD | `./data/brujula.db` | volumen `/data` |
