"""Dependance FastAPI: une session DB par requete, fermee automatiquement a la fin."""

from typing import Iterator

from sqlalchemy.orm import Session

from tennis_data.db import SessionLocal


def get_db() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
