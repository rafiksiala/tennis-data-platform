"""Schemas Pydantic pour les reponses de l'API. Volontairement separes du modele
SQLAlchemy (models.py): l'API expose ce qu'elle choisit, pas la structure interne brute."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class PlayerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    country_code: str | None = None


class PlayerDetailOut(PlayerOut):
    birth_date: date | None = None
    hand: str | None = None  # jamais disponible cote fournisseur pour l'instant (voir TODO.md)


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


class RankingSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tour: str
    snapshot_date: date
    rank: int | None = None
    points: int | None = None
    precision: str  # "weekly" (capture par nos soins) | "season_approx" (backfill)


class H2HOut(BaseModel):
    player1: PlayerOut
    player2: PlayerOut
    player1_wins: int
    player2_wins: int
    matches: list[MatchOut]


class SurfaceFormOut(BaseModel):
    surface: str
    matches: int
    wins: int
    win_rate: float | None = None


class PlayerFormOut(BaseModel):
    player_id: int
    as_of: datetime
    matches_considered: int

    matches_last_10: int
    win_rate_last_10: float | None = None
    matches_last_20: int
    win_rate_last_20: float | None = None
    matches_last_30: int
    win_rate_last_30: float | None = None

    matches_3m: int
    win_rate_3m: float | None = None
    matches_6m: int
    win_rate_6m: float | None = None
    matches_12m: int
    win_rate_12m: float | None = None

    by_surface: list[SurfaceFormOut]

    streak_type: str | None = None  # 'W' | 'L' | None
    streak_count: int
    days_since_last_match: int | None = None
    matches_last_30_days: int
