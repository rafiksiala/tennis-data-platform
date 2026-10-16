"""Petits constructeurs de lignes pour les tests base de donnees."""

from datetime import datetime

from sqlalchemy.orm import Session

from tennis_data.ingest.mapping import SOURCE
from tennis_data.models import Match, Player, Tournament, TournamentExternalId


def make_player(session: Session, name: str = "Test Player") -> Player:
    player = Player(full_name=name)
    session.add(player)
    session.flush()
    return player


def make_tournament(session: Session, **fields) -> Tournament:
    values = {"name": "Test Open", "tour": "atp", "season": 2026, "surface": "Hard", "external_series_key": "1000"}
    values.update(fields)
    tournament = Tournament(**values)
    session.add(tournament)
    session.flush()
    return tournament


def make_match(
    session: Session,
    tournament: Tournament,
    scheduled_at: datetime,
    player1: Player | None = None,
    player2: Player | None = None,
    winner: Player | None = None,
    **fields,
) -> Match:
    values = {"status": "finished", "round_code": "R32", "is_qualification": False}
    values.update(fields)
    match = Match(
        tournament_id=tournament.id,
        scheduled_at=scheduled_at,
        player1_id=player1.id if player1 else None,
        player2_id=player2.id if player2 else None,
        winner_id=winner.id if winner else None,
        **values,
    )
    session.add(match)
    session.flush()
    return match


def make_edition(session: Session, series_key: str, season: int, **fields) -> Tournament:
    """Edition telle que l'ingestion la cree: tournoi + cle externe {series_key}_{season}."""
    tournament = make_tournament(session, external_series_key=series_key, season=season, **fields)
    session.add(TournamentExternalId(tournament_id=tournament.id, source=SOURCE, external_id=f"{series_key}_{season}"))
    session.flush()
    return tournament
