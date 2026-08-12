"""
Modele de donnees tennis, independant du fournisseur.

Principes:
- Chaque entite a un ID interne (notre cle primaire). La correspondance vers l'ID
  d'un fournisseur externe (ex: player_key d'API-Tennis) vit dans une table
  <entite>_external_ids separee, avec une contrainte UNIQUE(source, external_id).
  Ca permet l'upsert idempotent et le changement de fournisseur sans tout renumeroter.
- Le H2H n'est PAS stocke: il se calcule par une requete sur `matches`
  (WHERE (player1_id=X AND player2_id=Y) OR (player1_id=Y AND player2_id=X)).
- Le classement precis a la date d'un match est une limitation reelle du fournisseur
  (confirmee par test le 2026-08-08): seul le classement courant est expose.
  Le champ RankingSnapshot.precision distingue donc:
    - "weekly"       -> capture par nos soins chaque semaine a partir du lancement (precis)
    - "season_approx"-> reconstitue depuis le rang de fin de saison fourni par get_players
                        pour les matchs backfilles avant le debut de notre capture (grossier)
- Meme logique pour les cotes: OddsSnapshot.is_retroactive distingue une cote recuperee
  apres coup (une seule valeur, sans horodatage fiable) d'une cote capturee par nous en
  temps reel (plusieurs valeurs dans le temps -> vraie evolution / ouverture / cloture).
"""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Joueurs
# ---------------------------------------------------------------------------
class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    country_code: Mapped[str | None] = mapped_column(String(10))
    birth_date: Mapped[date | None] = mapped_column(Date)
    hand: Mapped[str | None] = mapped_column(String(1))  # 'R', 'L', 'U' (inconnu)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    external_ids: Mapped[list["PlayerExternalId"]] = relationship(back_populates="player")


class PlayerExternalId(Base):
    __tablename__ = "player_external_ids"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_player_source_external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(50))  # ex: "api_tennis"
    external_id: Mapped[str] = mapped_column(String(50))

    player: Mapped["Player"] = relationship(back_populates="external_ids")


# ---------------------------------------------------------------------------
# Tournois (une ligne = une edition annuelle d'un tournoi, pas la serie historique)
# ---------------------------------------------------------------------------
class Tournament(Base):
    __tablename__ = "tournaments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    tour: Mapped[str] = mapped_column(String(30))  # atp | wta | challenger_men | challenger_women | itf_men | itf_women
    level: Mapped[str | None] = mapped_column(String(30))  # grand_slam | masters_1000 | 500 | 250 | challenger | itf (rempli progressivement)
    # cle brute du fournisseur pour la SERIE (ex: "Wimbledon" garde le meme tournament_key
    # d'API-Tennis chaque annee) - permet de regrouper toutes les editions d'un meme tournoi
    # sans avoir besoin d'une table series separee. La cle d'upsert (tournament_external_ids)
    # est elle composite {tournament_key}_{season} car chaque EDITION est une ligne ici.
    external_series_key: Mapped[str | None] = mapped_column(String(50), index=True)
    surface: Mapped[str | None] = mapped_column(String(20))  # hard | clay | grass | carpet
    country: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(100))
    season: Mapped[int | None] = mapped_column()
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    prize_money: Mapped[float | None] = mapped_column(Numeric(14, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    external_ids: Mapped[list["TournamentExternalId"]] = relationship(back_populates="tournament")


class TournamentExternalId(Base):
    __tablename__ = "tournament_external_ids"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_tournament_source_external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(50))
    external_id: Mapped[str] = mapped_column(String(50))

    tournament: Mapped["Tournament"] = relationship(back_populates="external_ids")


# ---------------------------------------------------------------------------
# Matchs
# ---------------------------------------------------------------------------
class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id"), index=True)
    round_raw: Mapped[str | None] = mapped_column(String(255))  # elargi le 2026-08-09: certains libelles Challenger depassaient 50
    round_code: Mapped[str | None] = mapped_column(String(10))  # R128,R64,R32,R16,QF,SF,F,RR,Q1,Q2,Q3...

    player1_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"), index=True)
    player2_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"), index=True)
    winner_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"))

    status: Mapped[str] = mapped_column(String(20))  # scheduled|live|finished|retired|walkover|cancelled|postponed
    status_raw: Mapped[str | None] = mapped_column(String(100))  # elargi le 2026-08-09, meme raison que round_raw
    is_qualification: Mapped[bool] = mapped_column(Boolean, default=False)

    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    score_raw: Mapped[str | None] = mapped_column(String(100))  # elargi le 2026-08-09, meme raison que round_raw
    duration_minutes: Mapped[int | None] = mapped_column()
    points_raw: Mapped[dict | None] = mapped_column(JSONB)  # point-by-point brut, non modelise relationnellement (cf. ADR dans le chat)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    tournament: Mapped["Tournament"] = relationship()
    external_ids: Mapped[list["MatchExternalId"]] = relationship(back_populates="match")
    sets: Mapped[list["MatchSet"]] = relationship(back_populates="match", order_by="MatchSet.set_number")
    statistics: Mapped[list["MatchStatistic"]] = relationship(back_populates="match")

    __table_args__ = (
        Index("ix_matches_player1_scheduled", "player1_id", "scheduled_at"),
        Index("ix_matches_player2_scheduled", "player2_id", "scheduled_at"),
    )


class MatchExternalId(Base):
    __tablename__ = "match_external_ids"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_match_source_external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(50))
    external_id: Mapped[str] = mapped_column(String(50))

    match: Mapped["Match"] = relationship(back_populates="external_ids")


class MatchSet(Base):
    __tablename__ = "match_sets"
    __table_args__ = (UniqueConstraint("match_id", "set_number", name="uq_match_set_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    set_number: Mapped[int] = mapped_column()
    player1_games: Mapped[int | None] = mapped_column()
    player2_games: Mapped[int | None] = mapped_column()
    tiebreak_player1_points: Mapped[int | None] = mapped_column()
    tiebreak_player2_points: Mapped[int | None] = mapped_column()

    match: Mapped["Match"] = relationship(back_populates="sets")


class MatchStatistic(Base):
    __tablename__ = "match_statistics"
    __table_args__ = (
        UniqueConstraint("match_id", "player_id", "stat_period", "stat_name", name="uq_match_stat"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    stat_period: Mapped[str] = mapped_column(String(20))  # "match" ou numero de set
    stat_name: Mapped[str] = mapped_column(String(50))  # nom canonique (aces, double_faults, ...)
    stat_value: Mapped[float | None] = mapped_column(Numeric(10, 2))
    stat_won: Mapped[int | None] = mapped_column()  # numerateur brut si fourni (ex: 39 sur "1st serve points won")
    stat_total: Mapped[int | None] = mapped_column()  # denominateur brut si fourni (ex: 57)
    raw_stat_name: Mapped[str | None] = mapped_column(String(100))  # libelle brut du fournisseur, pour tracabilite

    match: Mapped["Match"] = relationship(back_populates="statistics")


# ---------------------------------------------------------------------------
# Classements (historique construit par nous, voir docstring en tete de fichier)
# ---------------------------------------------------------------------------
class RankingSnapshot(Base):
    __tablename__ = "ranking_snapshots"
    __table_args__ = (
        UniqueConstraint("player_id", "tour", "snapshot_date", "source", name="uq_ranking_snapshot"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    tour: Mapped[str] = mapped_column(String(10))  # atp | wta
    snapshot_date: Mapped[date] = mapped_column(Date, index=True)
    rank: Mapped[int | None] = mapped_column()
    points: Mapped[int | None] = mapped_column()
    source: Mapped[str] = mapped_column(String(50))
    precision: Mapped[str] = mapped_column(String(20))  # "weekly" | "season_approx"


# ---------------------------------------------------------------------------
# Cotes (voir docstring en tete de fichier pour is_retroactive)
# ---------------------------------------------------------------------------
class OddsSnapshot(Base):
    __tablename__ = "odds_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    bookmaker: Mapped[str] = mapped_column(String(50))
    market: Mapped[str] = mapped_column(String(100))
    selection: Mapped[str] = mapped_column(String(50))
    odd_value: Mapped[float] = mapped_column(Numeric(10, 2))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_retroactive: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(50))

    __table_args__ = (Index("ix_odds_match_captured", "match_id", "captured_at"),)


# ---------------------------------------------------------------------------
# Journal brut (audit + capacite de rejouer/reparer une transformation)
# ---------------------------------------------------------------------------
class IngestRawLog(Base):
    __tablename__ = "ingest_raw_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(50))
    method: Mapped[str] = mapped_column(String(50))
    request_params: Mapped[dict] = mapped_column(JSONB)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    http_status: Mapped[int | None] = mapped_column()
    success: Mapped[bool] = mapped_column(Boolean)
    response_body: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (Index("ix_ingest_raw_log_method_fetched", "method", "fetched_at"),)


# ---------------------------------------------------------------------------
# Suivi des jobs d'ingestion (monitoring minimal)
# ---------------------------------------------------------------------------
class IngestRun(Base):
    __tablename__ = "ingest_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_name: Mapped[str] = mapped_column(String(50))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="running")  # running|success|partial|failed
    rows_inserted: Mapped[int] = mapped_column(default=0)
    rows_updated: Mapped[int] = mapped_column(default=0)
    api_calls_made: Mapped[int] = mapped_column(default=0)
    error_message: Mapped[str | None] = mapped_column(String(1000))
