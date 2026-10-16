"""Fixtures partagees.

Les tests marques `db` ont besoin d'un Postgres jetable, indique par TEST_DATABASE_URL
(jamais DATABASE_URL, pour ne jamais toucher la base de prod par erreur). Sans cette
variable, ils sont ignores: les tests de logique pure tournent partout, les tests base
tournent en CI (service Postgres 16 dans .github/workflows/ci.yml).

Chaque test tourne dans une transaction annulee a la fin: rien n'est jamais committe.
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from tennis_data.db import CONNECT_ARGS
from tennis_data.models import Base

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _test_database_url() -> str | None:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        return None
    host = make_url(url).host
    if host not in LOCAL_HOSTS:
        # garde-fou: les tests creent des tables et ecrivent des lignes
        raise pytest.UsageError(f"TEST_DATABASE_URL doit pointer vers une base locale jetable (host={host!r})")
    return url


@pytest.fixture(scope="session")
def db_engine():
    url = _test_database_url()
    if url is None:
        pytest.skip("TEST_DATABASE_URL non defini: tests base de donnees ignores")
    engine = create_engine(url, connect_args=CONNECT_ARGS)
    # sans effet si `alembic upgrade head` a deja cree le schema (cas de la CI)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    with db_engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


@pytest.fixture
def api_client(db_session):
    """Client HTTP de l'API, branche sur la session de test (meme transaction annulee)."""
    from tennis_data.api.deps import get_db
    from tennis_data.api.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
