"""Corrections auto-appliquees en continu (pas juste des scripts ponctuels)."""

from sqlalchemy import text
from sqlalchemy.orm import Session

# Voir scripts/fix_qualifying_finals.py pour le raisonnement complet: le champ
# event_qualification du fournisseur est souvent absent (null) plutot que False/True
# pour les matchs de qualifications, donc round_code='F' se retrouve applique a la fois
# a la vraie finale ET aux finales de qualifs (meme libelle brut "Final"). Heuristique
# fiable: dans un meme tournoi, la vraie finale est toujours le match 'F' le plus tardif.
_SQL_RECLASSIFY_QUALIFYING_FINALS = """
WITH ranked AS (
    SELECT id, tournament_id,
           row_number() OVER (
               PARTITION BY tournament_id ORDER BY scheduled_at DESC NULLS LAST, id DESC
           ) AS rn
    FROM matches
    WHERE round_code = 'F'
)
UPDATE matches
SET round_code = 'Q-F'
FROM ranked
WHERE matches.id = ranked.id AND ranked.rn > 1
RETURNING matches.id
"""


def reclassify_stale_qualifying_finals(session: Session) -> int:
    """A appeler apres chaque sync de fixtures: reclasse les finales de qualifs
    fraichement arrivees qui portaient encore round_code='F' par erreur. Idempotent."""
    result = session.execute(text(_SQL_RECLASSIFY_QUALIFYING_FINALS))
    return len(result.fetchall())
