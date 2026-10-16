"""Corrections auto-appliquees en continu (pas juste des scripts ponctuels)."""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

# Voir scripts/fix_qualifying_finals.py pour le contexte: le champ event_qualification
# du fournisseur est souvent absent (null) pour les matchs de qualifications, donc
# round_code='F' se retrouve a la fois sur la vraie finale ET sur les finales de qualifs
# (meme libelle brut "Final").
#
# Regle: la vraie finale est le DERNIER match de son edition. Tout 'F' programme avant le
# dernier match de l'edition est une finale de qualifs -> 'Q-F'; inversement un 'Q-F'
# pose par cette regle (is_qualification faux) qui se retrouve dernier match redevient 'F'.
#
# Avant le 2026-10-16 la regle etait "le 'F' le plus tardif est la vraie finale", fausse
# tant que l'edition est en cours: avant la vraie finale, le 'F' le plus tardif est une
# finale de qualifs, qui gardait donc 'F' (tournoi 2203 a l'etat QF, review 3.4). La
# nouvelle regle donne le meme resultat sur une edition terminee et corrige les editions
# en cours. Elle suppose des editions bien rattachees (un match d'une autre edition
# fausserait "le dernier match"): voir ingest/seasons.py.
#
# Seuls les matchs is_qualification faux sont concernes: un 'Q-F' venu du fournisseur
# (is_qualification vrai) n'est jamais touche.
_FINALS_CTE = """
WITH edition_last AS (
    SELECT tournament_id, max(scheduled_at) AS last_at
    FROM matches
    WHERE scheduled_at IS NOT NULL
    GROUP BY tournament_id
),
relabel AS (
    SELECT m.id,
           CASE WHEN m.scheduled_at >= e.last_at THEN 'F' ELSE 'Q-F' END AS new_code
    FROM matches m
    JOIN edition_last e ON e.tournament_id = m.tournament_id
    WHERE m.round_code IN ('F', 'Q-F')
      AND m.is_qualification IS NOT TRUE
      AND m.scheduled_at IS NOT NULL
)
"""

_SQL_PREVIEW = (
    _FINALS_CTE
    + """
SELECT m.id, m.tournament_id, m.round_code AS old_code, r.new_code
FROM matches m
JOIN relabel r ON r.id = m.id
WHERE m.round_code <> r.new_code
ORDER BY m.tournament_id, m.scheduled_at
"""
)

_SQL_APPLY = (
    _FINALS_CTE
    + """
UPDATE matches
SET round_code = relabel.new_code
FROM relabel
WHERE matches.id = relabel.id AND matches.round_code <> relabel.new_code
RETURNING matches.round_code
"""
)


@dataclass
class FinalsRelabel:
    demoted: int  # 'F' -> 'Q-F'
    promoted: int  # 'Q-F' -> 'F'

    @property
    def total(self) -> int:
        return self.demoted + self.promoted


def preview_finals_relabel(session: Session) -> list[dict]:
    """Ce que relabel_finals changerait, sans rien ecrire (une ligne par match)."""
    return [dict(row._mapping) for row in session.execute(text(_SQL_PREVIEW))]


def relabel_finals(session: Session) -> FinalsRelabel:
    """A appeler apres chaque sync de fixtures. Idempotent."""
    new_codes = [row.round_code for row in session.execute(text(_SQL_APPLY))]
    return FinalsRelabel(demoted=new_codes.count("Q-F"), promoted=new_codes.count("F"))
