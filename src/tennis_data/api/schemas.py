"""Schemas Pydantic pour les reponses de l'API. Volontairement separes du modele
SQLAlchemy (models.py): l'API expose ce qu'elle choisit, pas la structure interne brute."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class PlayerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    country_code: str | None = None


class TournamentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    tour: str
    level: str | None = None
    surface: str | None = None
    country: str | None = None
    city: str | None = None
    season: int | None = None


class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scheduled_at: datetime | None = None
    status: str
    round_code: str | None = None
    round_raw: str | None = None
    score_raw: str | None = None
    is_qualification: bool
    tournament: TournamentOut
    player1: PlayerOut | None = None
    player2: PlayerOut | None = None
    winner_id: int | None = None


class MatchListOut(BaseModel):
    total: int
    limit: int
    offset: int
    results: list[MatchOut]


class SetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    set_number: int
    player1_games: int | None = None
    player2_games: int | None = None
    tiebreak_player1_points: int | None = None
    tiebreak_player2_points: int | None = None


class StatisticOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    player_id: int
    stat_period: str
    stat_name: str
    stat_value: float | None = None
    stat_won: int | None = None
    stat_total: int | None = None


class OddsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bookmaker: str
    market: str
    selection: str
    odd_value: float
    captured_at: datetime
    is_retroactive: bool


class MatchDetailOut(MatchOut):
    sets: list[SetOut] = []
    statistics: list[StatisticOut] = []
    odds: list[OddsOut] = []
