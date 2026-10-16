"""
Saison d'une edition de tournoi, deduite de la date du match.

Le champ tournament_season du fournisseur n'est pas fiable: 87 matchs de l'US Open 2026
(R128 -> QF, joues en septembre 2026) etaient ranges sous l'edition 2025 (review 3.3).
Comme la cle d'une edition est {tournament_key}_{saison}, une saison fausse coupe une
edition en deux lignes `tournaments`.
"""

from datetime import date

# La saison commence fin decembre (United Cup, Brisbane, premiers Challengers de janvier
# qui demarrent le 29-30/12): un match joue a partir du 26 decembre compte pour la saison
# suivante. En pratique aucun tournoi des circuits suivis ne chevauche le 26/12 (treve de
# Noel), donc la regle ne coupe pas une edition en deux.
SEASON_ROLLOVER_DAY = 26  # jour de decembre a partir duquel on bascule sur l'annee suivante


def season_for_date(day: date) -> int:
    if day.month == 12 and day.day >= SEASON_ROLLOVER_DAY:
        return day.year + 1
    return day.year
