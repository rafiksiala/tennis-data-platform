"""Trace des reparations appliquees: une ligne ingest_runs 'repair:<nom>' en statut success."""

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from tennis_data.models import IngestRun


class RepairRefused(Exception):
    """Une precondition n'est pas remplie: rien n'a ete ecrit."""


def _job_name(repair: str) -> str:
    return f"repair:{repair}"


def applied_at(session: Session, repair: str) -> datetime | None:
    return (
        session.query(func.max(IngestRun.finished_at))
        .filter(IngestRun.job_name == _job_name(repair), IngestRun.status == "success")
        .scalar()
    )


def record_applied(session: Session, repair: str, rows_updated: int, note: str | None = None) -> None:
    """A appeler dans la MEME transaction que la reparation: les deux sont committees ensemble."""
    now = datetime.now(timezone.utc)
    session.add(
        IngestRun(
            job_name=_job_name(repair),
            started_at=now,
            finished_at=now,
            status="success",
            rows_updated=rows_updated,
            error_message=note,  # pas de colonne dediee: on y garde les parametres utilises
        )
    )
    session.flush()
