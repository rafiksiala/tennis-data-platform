"""
Reparation 4/4: reetiquetage QF/SF -> Q-QF/Q-SF des matchs de qualifs etiquetes comme
tableau principal, avec la regle de ingest/maintenance.py ("un QF/SF programme avant le
premier R16 du tableau principal de son edition est un match de qualifs").

Comme celle des finales, la regle situe chaque match dans son edition: elle suppose des
editions bien rattachees (reparation 'editions'). On la place apres 'finals' pour garder
un ordre lineaire, les deux regles etant independantes. Naturellement idempotente (meme
regle que celle qui tourne apres chaque daily_sync).
"""

from collections import Counter

from sqlalchemy.orm import Session

from tennis_data.ingest.maintenance import QualifyingRelabel, preview_qualifying_relabel, relabel_qualifying_rounds
from tennis_data.models import Tournament
from tennis_data.repairs import finals
from tennis_data.repairs.markers import RepairRefused, applied_at, record_applied

NAME = "qualifying_rounds"


def preview(session: Session) -> list[dict]:
    """Une ligne par edition touchee: tournament_id, name, tour, season, demoted, promoted."""
    changes = preview_qualifying_relabel(session)
    demoted = Counter(c["tournament_id"] for c in changes if c["new_code"].startswith("Q-"))
    promoted = Counter(c["tournament_id"] for c in changes if not c["new_code"].startswith("Q-"))
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


def apply(session: Session) -> QualifyingRelabel:
    if applied_at(session, finals.NAME) is None:
        raise RepairRefused("appliquer d'abord la reparation finals (ordre lineaire, editions rattachees)")
    result = relabel_qualifying_rounds(session)
    record_applied(
        session, NAME, result.total, note=f"{result.demoted} QF/SF->Q-QF/Q-SF, {result.promoted} Q-QF/Q-SF->QF/SF"
    )
    return result
