"""
Fraicheur des donnees, exposee par /health.

L'ingestion s'est arretee le 2026-09-09 sans que rien ne le signale pendant 5 semaines
(review 3.1): /health dit maintenant depuis quand chaque circuit n'a pas ete synchronise,
et quand chaque job a reussi pour la derniere fois.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from tennis_data.models import IngestRun, Match, Tournament

# Les jobs quotidiens tournent toutes les 24 h: plus de 36 h sans synchro = au moins un run rate.
STALE_AFTER = timedelta(hours=36)


def _iso_utc(value: datetime | None) -> str | None:
    """ISO 8601 en '...Z' (ADR-0003), comme les autres reponses de l'API."""
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def data_freshness(session: Session, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)

    tours = {}
    last_sync_by_tour = (
        session.query(Tournament.tour, func.max(Match.last_synced_at))
        .join(Match, Match.tournament_id == Tournament.id)
        .group_by(Tournament.tour)
        .order_by(Tournament.tour)
    )
    for tour, last_synced_at in last_sync_by_tour:
        age = now - last_synced_at if last_synced_at else None
        tours[tour] = {
            "last_synced_at": _iso_utc(last_synced_at),
            "age_hours": round(age.total_seconds() / 3600, 1) if age is not None else None,
            "stale": age is None or age > STALE_AFTER,
        }

    # une famille par job: "daily_sync:atp_singles" -> "daily_sync" (quelques dizaines de noms au plus)
    last_success_by_family: dict[str, datetime] = {}
    for job_name, finished_at in (
        session.query(IngestRun.job_name, func.max(IngestRun.finished_at))
        .filter(IngestRun.status == "success", IngestRun.finished_at.isnot(None))
        .group_by(IngestRun.job_name)
    ):
        family = job_name.split(":", 1)[0]
        if family not in last_success_by_family or finished_at > last_success_by_family[family]:
            last_success_by_family[family] = finished_at

    return {
        "stale": not tours or any(t["stale"] for t in tours.values()),
        "checked_at": _iso_utc(now),
        "stale_after_hours": STALE_AFTER.total_seconds() / 3600,
        "tours": tours,
        "last_successful_runs": {
            family: _iso_utc(finished_at) for family, finished_at in sorted(last_success_by_family.items())
        },
    }


class FreshnessCache:
    """/health est appele toutes les quelques secondes par Render: on ne recalcule la
    fraicheur (agregat sur toute la table matches) qu'une fois par `ttl`."""

    def __init__(self, ttl: timedelta):
        self.ttl = ttl
        self._value: dict | None = None
        self._computed_at: datetime | None = None

    def get(self, session: Session, now: datetime | None = None) -> dict:
        now = now or datetime.now(timezone.utc)
        if self._value is not None and self._computed_at is not None and now - self._computed_at < self.ttl:
            return self._value
        try:
            value = data_freshness(session, now)
        except SQLAlchemyError:
            # pas mis en cache: on retentera au prochain appel
            return {"error": "database unreachable"}
        self._value, self._computed_at = value, now
        return value

    def clear(self) -> None:
        self._value = self._computed_at = None
