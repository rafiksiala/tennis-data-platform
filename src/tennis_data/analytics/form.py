"""
Indicateurs de forme, calcules a la volee (pas de pre-calcul/cache: le volume de
matchs par joueur reste petit - quelques centaines au maximum - donc le cout de calcul
est negligeable, pas besoin de complexifier avec une table materialisee pour l'instant).

Chaque fonction accepte un parametre `as_of`: la date jusqu'a laquelle regarder (tout
ce qui vient apres est ignore). Concu des le depart pour le backtesting a venir (etape
14 du plan initial) - "ce qu'on savait avant un match donne" sans dupliquer cette
logique plus tard. Par defaut, as_of = maintenant.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from tennis_data.models import Match, Tournament

MAX_MATCHES_LOOKBACK = 200  # large marge au-dessus de toutes les fenetres calculees ici


@dataclass
class SurfaceForm:
    surface: str
    matches: int
    wins: int

    @property
    def win_rate(self) -> float | None:
        return self.wins / self.matches if self.matches else None


@dataclass
class PlayerForm:
    player_id: int
    as_of: datetime
    matches_considered: int  # taille de l'echantillon regarde (fenetre bornee par MAX_MATCHES_LOOKBACK)

    last_n: dict[int, tuple[int, int]]  # N -> (victoires, matchs) pour N in (10,20,30)
    window_months: dict[int, tuple[int, int]]  # mois -> (victoires, matchs) pour 3,6,12
    by_surface: dict[str, SurfaceForm]
    streak_type: str | None  # 'W' | 'L' | None si aucun match
    streak_count: int
    days_since_last_match: int | None
    matches_last_30_days: int

    def win_rate_last_n(self, n: int) -> float | None:
        wins, matches = self.last_n.get(n, (0, 0))
        return wins / matches if matches else None

    def win_rate_window(self, months: int) -> float | None:
        wins, matches = self.window_months.get(months, (0, 0))
        return wins / matches if matches else None


def compute_player_form(session: Session, player_id: int, as_of: datetime | None = None) -> PlayerForm:
    as_of = as_of or datetime.now(timezone.utc)

    rows = (
        session.query(Match.scheduled_at, Match.winner_id, Tournament.surface)
        .join(Tournament, Tournament.id == Match.tournament_id)
        .filter(
            or_(Match.player1_id == player_id, Match.player2_id == player_id),
            Match.status == "finished",
            Match.scheduled_at.isnot(None),
            Match.scheduled_at <= as_of,
        )
        .order_by(Match.scheduled_at.desc())
        .limit(MAX_MATCHES_LOOKBACK)
        .all()
    )

    last_n: dict[int, tuple[int, int]] = {}
    for n in (10, 20, 30):
        subset = rows[:n]
        wins = sum(1 for r in subset if r.winner_id == player_id)
        last_n[n] = (wins, len(subset))

    window_months: dict[int, tuple[int, int]] = {}
    for months in (3, 6, 12):
        cutoff = as_of - timedelta(days=months * 30)
        subset = [r for r in rows if r.scheduled_at >= cutoff]
        wins = sum(1 for r in subset if r.winner_id == player_id)
        window_months[months] = (wins, len(subset))

    by_surface: dict[str, SurfaceForm] = {}
    for r in rows:
        if not r.surface:
            continue
        sf = by_surface.setdefault(r.surface, SurfaceForm(surface=r.surface, matches=0, wins=0))
        sf.matches += 1
        if r.winner_id == player_id:
            sf.wins += 1

    streak_type: str | None = None
    streak_count = 0
    for r in rows:
        result = "W" if r.winner_id == player_id else "L"
        if streak_type is None:
            streak_type = result
            streak_count = 1
        elif result == streak_type:
            streak_count += 1
        else:
            break

    days_since_last_match = (as_of - rows[0].scheduled_at).days if rows else None
    thirty_days_ago = as_of - timedelta(days=30)
    matches_last_30_days = sum(1 for r in rows if r.scheduled_at >= thirty_days_ago)

    return PlayerForm(
        player_id=player_id,
        as_of=as_of,
        matches_considered=len(rows),
        last_n=last_n,
        window_months=window_months,
        by_surface=by_surface,
        streak_type=streak_type,
        streak_count=streak_count,
        days_since_last_match=days_since_last_match,
        matches_last_30_days=matches_last_30_days,
    )
