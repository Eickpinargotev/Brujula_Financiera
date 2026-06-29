#!/bin/sh
# Arranca como root SOLO para asegurar que el volumen /data sea escribible por la app
# (en la nube el volumen se monta como root) y luego baja al usuario no-root `brujula`.
set -e

mkdir -p /data
chown -R brujula:brujula /data 2>/dev/null || true

exec gosu brujula "$@"
