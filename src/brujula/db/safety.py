"""Protección del archivo activo y respaldos SQLite consistentes, incluido el WAL."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy.engine import make_url


def database_path(url: str) -> Path:
    parsed = make_url(url)
    if parsed.drivername != "sqlite+aiosqlite" or not parsed.database:
        raise RuntimeError("La aplicación requiere una base SQLite persistente.")
    path = Path(parsed.database)
    if not path.is_absolute() or parsed.query:
        raise RuntimeError("DATABASE_URL debe usar un archivo absoluto, sin parámetros.")
    return path.resolve()


def check_database(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(
            f"Falta la base de datos existente: {path}. "
            "Revisa el volumen; no se creará una base vacía automáticamente."
        )
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as conn:
        if conn.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise RuntimeError("La base de datos no superó la comprobación de integridad.")
        if not conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='movimientos'"
        ).fetchone():
            raise RuntimeError("El archivo no es una base de Brújula inicializada.")


def backup_database(path: Path, reason: str = "before-write") -> Path:
    """No copia el .db en crudo: la API backup incluye transacciones confirmadas del WAL.

    No se eliminan respaldos automáticamente. Si falta espacio, se bloquea la escritura
    que pidió el respaldo antes de modificar los datos del usuario.
    """
    check_database(path)
    folder = path.parent / "backups"
    folder.mkdir(mode=0o700, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    target = folder / f"{stamp}-{reason}-{uuid4().hex[:8]}.sqlite"
    with (
        closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as source,
        closing(sqlite3.connect(target)) as dest,
    ):
        source.backup(dest)
        if dest.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise RuntimeError("No se pudo verificar el respaldo de seguridad.")
    target.chmod(0o600)
    return target
