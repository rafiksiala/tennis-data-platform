"""
Reparation 3/3: reetiquetage F / Q-F de toutes les editions avec la regle corrigee
("la vraie finale est le dernier match de son edition", ingest/maintenance.py, review 3.4).

La regle compare chaque finale au dernier match de son edition: elle suppose des
editions bien rattachees, d'ou l'obligation de passer la reparation 'editions' avant.
Naturellement idempotente (meme regle que celle qui tourne apres chaque daily_sync).
"""

from collections import Counter

from sqlalchemy.orm import Session

from tennis_data.ingest.maintenance import FinalsRelabel, preview_finals_relabel, relabel_finals
from tennis_data.models import Tournament
from tennis_data.repairs import editions
from tennis_data.repairs.markers import RepairRefused, applied_at, record_applied

NAME = "finals"


def preview(session: Session) -> list[dict]:
    """Une ligne par edition touchee: tournament_id, name, tour, season, demoted, promoted."""
    changes = preview_finals_relabel(session)
    demoted = Counter(c["tournament_id"] for c in changes if c["new_code"] == "Q-F")
    promoted = Counter(c["tournament_id"] for c in changes if c["new_code"] == "F")
    ids = sorted(set(demoted) | set(promoted))
    tournaments = {t.id: t for t in session.query(Tournament).filter(Tournament.id.in_(ids))} if ids else {}
    return [
        {
            "tournament_id": tid,
            "name": tournaments[tid].name,
            "tour": tournaments[tid].tour,
            "season": tournaments[tid].season,
            "demoted": demoted[tid],
            "promoted": promoted[tid],
        }
        for tid in ids
    ]


def apply(session: Session) -> FinalsRelabel:
    if applied_at(session, editions.NAME) is None:
        raise RepairRefused("appliquer d'abord la reparation editions (la regle suppose des editions bien rattachees)")
    result = relabel_finals(session)
    record_applied(session, NAME, result.total, note=f"{result.demoted} F->Q-F, {result.promoted} Q-F->F")
    return result
