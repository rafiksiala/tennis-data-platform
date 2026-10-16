"""Connexion base de donnees : engine SQLAlchemy + fabrique de sessions."""

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from tennis_data.config import DATABASE_URL

# Session Postgres en UTC quel que soit le reglage du serveur (ADR-0003): les timestamptz
# reviennent en UTC (donc serialises en "...Z" par l'API) et une valeur sans fuseau est lue
# comme de l'UTC.
CONNECT_ARGS = {"options": "-c timezone=UTC"}

engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=CONNECT_ARGS)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def get_session() -> Session:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
