"""
Reparation 1/3: matches.scheduled_at contient l'heure de Berlin du fournisseur stockee
comme si c'etait de l'UTC (review 3.5, ADR-0003). On la relit comme une heure de Berlin
et on la convertit en vrai UTC: 17:10Z (finale de Wimbledon 2026, match 32529) -> 15:10Z.

Ce decalage n'est PAS idempotent par nature (le rejouer decalerait une 2e fois): il est
protege par la trace 'repair:scheduled_at_utc' dans ingest_runs, et ne touche que les
lignes synchronisees avant `cutoff` (les lignes ecrites par le code corrige sont deja en
UTC). Le SQL donne exactement le meme instant que l'ingestion corrigee, y compris aux
changements d'heure (voir timeutil.wall_time_to_utc et tests/test_timeutil.py).
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from tennis_data.ingest.mapping import PROVIDER_TZ
from tennis_data.repairs.markers import RepairRefused, applied_at, record_applied

NAME = "scheduled_at_utc"

# Lendemain du gel de la base: aucune synchro n'a tourne depuis, donc toute ligne
# synchronisee avant cette date a ete ecrite par l'ancien code (heure de Berlin).
DEFAULT_CUTOFF = datetime(2026, 9, 10, tzinfo=timezone.utc)

# Match de reference connu (review 3.5): finale de Wimbledon 2026, 17:10 a Berlin.
DEFAULT_SAMPLE_IDS = (32529,)

_SHIFTED = "((scheduled_at AT TIME ZONE 'UTC') AT TIME ZONE :provider_tz)"
_TO_SHIFT = "scheduled_at IS NOT NULL AND (last_synced_at IS NULL OR last_synced_at < :cutoff)"


@dataclass
class Preview:
    cutoff: datetime
    already_applied_at: datetime | None
    matches_with_time: int
    to_shift: int
    shift_2h: int  # heure d'ete
    shift_1h: int  # heure d'hiver
    synced_after_cutoff: int  # ecrites apres cutoff: laissees telles quelles
    samples: list[dict]


def _params(cutoff: datetime) -> dict:
    return {"cutoff": cutoff, "provider_tz": PROVIDER_TZ.key}


def preview(session: Session, cutoff: datetime = DEFAULT_CUTOFF, sample_ids=DEFAULT_SAMPLE_IDS) -> Preview:
    counts = (
        session.execute(
            text(f"""
                SELECT
                    count(*) FILTER (WHERE scheduled_at IS NOT NULL) AS matches_with_time,
                    count(*) FILTER (WHERE {_TO_SHIFT}) AS to_shift,
                    count(*) FILTER (WHERE {_TO_SHIFT} AND scheduled_at - {_SHIFTED} = interval '2 hours') AS shift_2h,
                    count(*) FILTER (WHERE {_TO_SHIFT} AND scheduled_at - {_SHIFTED} = interval '1 hour') AS shift_1h,
                    count(*) FILTER (WHERE scheduled_at IS NOT NULL AND last_synced_at >= :cutoff)
                        AS synced_after_cutoff
                FROM matches
            """),
            _params(cutoff),
        )
        .mappings()
        .one()
    )
    samples = (
        []
        if not sample_ids
        else [
            dict(row)
            for row in session.execute(
                text(f"""
                SELECT id, scheduled_at AS stored, {_SHIFTED} AS repaired, ({_TO_SHIFT}) AS will_shift
                FROM matches
                WHERE id = ANY(:ids)
                ORDER BY id
            """),
                {**_params(cutoff), "ids": list(sample_ids)},
            ).mappings()
        ]
    )
    return Preview(cutoff=cutoff, already_applied_at=applied_at(session, NAME), samples=samples, **counts)


def apply(session: Session, cutoff: datetime = DEFAULT_CUTOFF, cutoff_is_explicit: bool = False) -> int:
    """Decale les lignes et laisse la trace, dans la transaction de l'appelant (qui commit).
    Retourne le nombre de lignes decalees."""
    done_at = applied_at(session, NAME)
    if done_at is not None:
        raise RepairRefused(f"deja appliquee le {done_at:%Y-%m-%d %H:%M} UTC: la rejouer decalerait une 2e fois")

    synced_after = session.execute(
        text("SELECT count(*) FROM matches WHERE scheduled_at IS NOT NULL AND last_synced_at >= :cutoff"),
        {"cutoff": cutoff},
    ).scalar_one()
    if synced_after and not cutoff_is_explicit:
        raise RepairRefused(
            f"{synced_after} matchs synchronises apres le {cutoff:%Y-%m-%d}: l'ingestion a repris depuis le gel. "
            "Impossible de savoir s'ils ont ete ecrits par l'ancien code (Berlin) ou le nouveau (UTC). "
            "Relancer avec --cutoff = date de deploiement du correctif UTC."
        )

    shifted = session.execute(
        text(f"UPDATE matches SET scheduled_at = {_SHIFTED} WHERE {_TO_SHIFT}"), _params(cutoff)
    ).rowcount
    record_applied(session, NAME, shifted, note=f"cutoff={cutoff.isoformat()} provider_tz={PROVIDER_TZ.key}")
    return shifted
