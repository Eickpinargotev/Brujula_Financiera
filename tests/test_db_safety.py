"""Guardas de persistencia sobre archivos temporales, nunca sobre los datos reales."""

import sqlite3
from pathlib import Path

import pytest

from brujula.db.safety import backup_database, check_database, database_path


def test_refuses_missing_or_empty_database(tmp_path: Path) -> None:
    path = tmp_path / "missing.db"
    with pytest.raises(RuntimeError, match="Falta la base"):
        check_database(path)
    assert not path.exists()
    path.touch()
    with pytest.raises(RuntimeError, match="Falta la base"):
        check_database(path)


@pytest.mark.parametrize("url", [
    "sqlite+aiosqlite:///relative.db", "sqlite+aiosqlite:///:memory:",
    "sqlite+aiosqlite://", "sqlite+aiosqlite:////tmp/a.db?mode=ro",
])
def test_refuses_ambiguous_database_locations(url: str) -> None:
    with pytest.raises(RuntimeError):
        database_path(url)


def test_backups_include_committed_wal_and_preserve_previous_version(tmp_path: Path) -> None:
    path = tmp_path / "active.db"
    with sqlite3.connect(path) as source:
        source.execute("PRAGMA journal_mode=WAL")
        source.execute("CREATE TABLE movimientos(id INTEGER PRIMARY KEY, monto REAL)")
        source.execute("INSERT INTO movimientos VALUES(1, 200)")
        source.commit()
        first = backup_database(path)
        source.execute("UPDATE movimientos SET monto=250")
        source.commit()
        second = backup_database(path)
        assert first != second
        with sqlite3.connect(first) as old, sqlite3.connect(second) as new:
            assert old.execute("SELECT monto FROM movimientos").fetchone() == (200,)
            assert new.execute("SELECT monto FROM movimientos").fetchone() == (250,)


def test_refuses_corrupt_or_unrelated_database(tmp_path: Path) -> None:
    path = tmp_path / "unrelated.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE other(id INTEGER)")
    with pytest.raises(RuntimeError, match="no es una base"):
        check_database(path)
