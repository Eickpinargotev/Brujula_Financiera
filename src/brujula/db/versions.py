"""Huella de los campos persistidos para detectar ediciones desde una vista antigua."""

import hashlib
import json

from brujula.db.models import Movimiento, Transfer


def record_version(record: Movimiento | Transfer) -> str:
    fields = {c.name: getattr(record, c.name) for c in record.__table__.columns}
    return hashlib.sha256(json.dumps(fields, sort_keys=True, default=str).encode()).hexdigest()
