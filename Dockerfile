# syntax=docker/dockerfile:1

# ---- Base ---------------------------------------------------------------
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src

# PYTHONPATH=/app/src hace que el código en ./src tenga prioridad sobre la copia
# instalada: así el bind-mount de desarrollo (--reload) toma efecto, y en producción
# se usa el ./src copiado en la imagen.

# Dependencia del sistema mínima: gosu permite bajar de root a usuario no-root
# después de ajustar permisos del volumen.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---- Builder: instala dependencias -------------------------------------
FROM base AS builder

ARG INSTALL_DEV=false
COPY pyproject.toml ./
COPY src ./src
RUN pip install --upgrade pip \
    && if [ "$INSTALL_DEV" = "true" ]; then pip install ".[dev]"; else pip install .; fi

# ---- Runtime ------------------------------------------------------------
FROM base AS runtime

# Usuario no-root
RUN useradd --create-home --uid 1000 brujula

# Copia el entorno con las dependencias ya instaladas
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY src ./src
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Volumen para la base de datos (SQLite)
RUN mkdir -p /data && chown -R brujula:brujula /data /app
VOLUME ["/data"]

# NO fijamos USER: el contenedor inicia como root, el entrypoint ajusta permisos del
# volumen y luego ejecuta la app como `brujula` (no-root) vía gosu.
EXPOSE 8000

# Healthcheck: verifica la app Y la base de datos (/health hace SELECT 1).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status==200 else 1)"

ENTRYPOINT ["/entrypoint.sh"]
# --proxy-headers: detrás del proxy de EasyPanel, ve la IP real del cliente (rate-limit).
CMD ["uvicorn", "brujula.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
