"""
API de lecture pour le calendrier/resultats. Sert notre modele normalise (jamais le
format brut du fournisseur) - voir models.py pour le raisonnement.

Lancer en local:
    uvicorn tennis_data.api.main:app --reload --app-dir src

Documentation interactive une fois lance: http://localhost:8000/docs
"""

from datetime import date, datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from tennis_data.analytics.form import compute_player_form
from tennis_data.api.deps import get_db
from tennis_data.api.schemas import (
    H2HOut,
    MatchDetailOut,
    MatchListOut,
    PlayerDetailOut,
    PlayerFormOut,
    PlayerOut,
    RankingSnapshotOut,
    SurfaceFormOut,
    TournamentOut,
)
from tennis_data.models import Match, MatchStatistic, OddsSnapshot, Player, RankingSnapshot, Tournament

app = FastAPI(title="Tennis Data API", version="0.1.0")

# Restreint au frontend deploye + dev local (voir TODO.md pour le raisonnement:
# CORS ne protege pas des donnees sensibles ici, ca evite juste que d'autres sites
# consomment gratuitement l'API depuis le navigateur d'un visiteur).
ALLOWED_ORIGINS = [
    "https://tennis-data-platform-gby1.onrender.com",
    "http://localhost:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/matches", response_model=MatchListOut)
def list_matches(
    db: Session = Depends(get_db),
    date_filter: date | None = Query(None, alias="date", description="Un seul jour, format YYYY-MM-DD"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    tour: str | None = Query(None, description="atp | wta | challenger_men | challenger_women | itf_men | itf_women"),
    surface: str | None = Query(None),
    round_code: str | None = Query(None),
    status: str | None = Query(None, description="scheduled | live | finished | retired | walkover | cancelled"),
    tournament_id: int | None = Query(None),
    player_id: int | None = Query(None, description="Matchs impliquant ce joueur (comme player1 OU player2)"),
    q: str | None = Query(None, description="Recherche par nom de joueur (partiel, insensible a la casse)"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    # Pas de joinedload ici: .count() n'a pas besoin des jointures (chaque match a
    # exactement un tournoi/player1/player2, donc ca ne change pas le compte), mais
    # SQLAlchemy les inclut quand meme dans la requete de comptage si on les a ajoutees
    # via .options() sur cette meme query -> ~7x plus lent sur 100k+ matchs, au point de
    # timeout sur le plan gratuit Render (trouve par test le 2026-08-13). Le joinedload
    # n'est ajoute que plus bas, juste avant le .all() final qui en a vraiment besoin.
    query = db.query(Match)

    if date_filter:
        query = query.filter(
            Match.scheduled_at >= datetime.combine(date_filter, datetime.min.time()),
            Match.scheduled_at < datetime.combine(date_filter + timedelta(days=1), datetime.min.time()),
        )
    if date_from:
        query = query.filter(Match.scheduled_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.filter(Match.scheduled_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time()))
    if status:
        query = query.filter(Match.status == status)
    if round_code:
        query = query.filter(Match.round_code == round_code)
    if tournament_id:
        query = query.filter(Match.tournament_id == tournament_id)
    if player_id:
        query = query.filter(or_(Match.player1_id == player_id, Match.player2_id == player_id))

    if tour or surface:
        query = query.join(Tournament, Match.tournament_id == Tournament.id)
        if tour:
            query = query.filter(Tournament.tour == tour)
        if surface:
            query = query.filter(Tournament.surface == surface)

    if q:
        query = query.join(Player, or_(Match.player1_id == Player.id, Match.player2_id == Player.id)).filter(
            Player.full_name.ilike(f"%{q}%")
        )

    # .distinct() n'est necessaire QUE pour la recherche par nom (q): c'est le seul
    # filtre qui fait un join pouvant dupliquer une ligne Match (si player1 ET player2
    # correspondent tous les deux).
    total = query.distinct(Match.id).count() if q else query.count()
    # PAS de .nullslast(): aucun match n'a scheduled_at NULL en pratique (verifie le
    # 2026-08-13), et cette clause a elle seule empeche Postgres d'utiliser l'index sur
    # scheduled_at (Index Scan Backward, ~2ms) et le force a tout scanner + trier
    # (Seq Scan + sort, ~4.5s) - confirme par EXPLAIN ANALYZE. Si des NULL apparaissent
    # un jour, mieux vaut le re-tester explicitement qu'ajouter ça "au cas ou".
    query = query.order_by(Match.scheduled_at.desc())
    if q:
        query = query.distinct()

    # PAGINER D'ABORD, ENRICHIR ENSUITE: joindre tournament/player1/player2 puis trier+
    # limiter force Postgres a construire le JOIN complet (109k+ lignes) avant de pouvoir
    # trier et limiter, ce qui l'empeche d'utiliser l'index sur scheduled_at (confirme par
    # EXPLAIN ANALYZE le 2026-08-13: Parallel Seq Scan sur toute la table `matches` malgre
    # un LIMIT 2). En triant/limitant D'ABORD sur Match seul (index-friendly, rapide), puis
    # en rechargeant seulement cette petite page avec les jointures, le join ne porte plus
    # que sur <=200 lignes au lieu de 109k.
    page_ids = [row[0] for row in query.with_entities(Match.id).offset(offset).limit(limit).all()]
    if not page_ids:
        matches = []
    else:
        by_id = {
            m.id: m
            for m in db.query(Match)
            .options(joinedload(Match.tournament), joinedload(Match.player1), joinedload(Match.player2))
            .filter(Match.id.in_(page_ids))
            .all()
        }
        matches = [by_id[i] for i in page_ids if i in by_id]

    return MatchListOut(total=total, limit=limit, offset=offset, results=matches)


@app.get("/matches/{match_id}", response_model=MatchDetailOut)
def get_match(match_id: int, db: Session = Depends(get_db)):
    match = (
        db.query(Match)
        .options(
            joinedload(Match.tournament),
            joinedload(Match.player1),
            joinedload(Match.player2),
            joinedload(Match.sets),
        )
        .filter(Match.id == match_id)
        .one_or_none()
    )
    if not match:
        raise HTTPException(status_code=404, detail="Match introuvable")

    statistics = db.query(MatchStatistic).filter(MatchStatistic.match_id == match_id).all()
    odds = (
        db.query(OddsSnapshot)
        .filter(OddsSnapshot.match_id == match_id)
        .order_by(OddsSnapshot.captured_at.desc())
        .limit(500)
        .all()
    )

    result = MatchDetailOut.model_validate(match)
    result.statistics = statistics
    result.odds = odds
    return result


@app.get("/tournaments", response_model=list[TournamentOut])
def list_tournaments(
    db: Session = Depends(get_db),
    season: int | None = Query(None),
    tour: str | None = Query(None),
    q: str | None = Query(None, description="Recherche par nom, partielle"),
    limit: int = Query(100, le=500),
):
    query = db.query(Tournament)
    if season:
        query = query.filter(Tournament.season == season)
    if tour:
        query = query.filter(Tournament.tour == tour)
    if q:
        query = query.filter(Tournament.name.ilike(f"%{q}%"))
    return query.order_by(Tournament.start_date.desc().nullslast()).limit(limit).all()


@app.get("/players", response_model=list[PlayerOut])
def search_players(
    db: Session = Depends(get_db),
    q: str = Query(..., min_length=2, description="Recherche par nom, partielle"),
    limit: int = Query(20, le=100),
):
    return (
        db.query(Player)
        .filter(Player.full_name.ilike(f"%{q}%"))
        .order_by(Player.full_name)
        .limit(limit)
        .all()
    )


@app.get("/players/{player_id}", response_model=PlayerDetailOut)
def get_player(player_id: int, db: Session = Depends(get_db)):
    player = db.query(Player).filter(Player.id == player_id).one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="Joueur introuvable")
    return player


@app.get("/players/{player_id}/form", response_model=PlayerFormOut)
def player_form(
    player_id: int,
    db: Session = Depends(get_db),
    as_of: datetime | None = Query(
        None, description="Ne regarde que les matchs termines avant cette date (par defaut: maintenant)"
    ),
):
    """Indicateurs de forme (win rate 10/20/30 derniers matchs, par fenetre de temps,
    par surface, serie en cours, repos). Voir tennis_data/analytics/form.py: le parametre
    as_of est deja pense pour le backtesting a venir, pas seulement l'usage "live"."""
    player = db.query(Player).filter(Player.id == player_id).one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="Joueur introuvable")

    form = compute_player_form(db, player_id, as_of)
    return PlayerFormOut(
        player_id=form.player_id,
        as_of=form.as_of,
        matches_considered=form.matches_considered,
        matches_last_10=form.last_n[10][1],
        win_rate_last_10=form.win_rate_last_n(10),
        matches_last_20=form.last_n[20][1],
        win_rate_last_20=form.win_rate_last_n(20),
        matches_last_30=form.last_n[30][1],
        win_rate_last_30=form.win_rate_last_n(30),
        matches_3m=form.window_months[3][1],
        win_rate_3m=form.win_rate_window(3),
        matches_6m=form.window_months[6][1],
        win_rate_6m=form.win_rate_window(6),
        matches_12m=form.window_months[12][1],
        win_rate_12m=form.win_rate_window(12),
        by_surface=[
            SurfaceFormOut(surface=s.surface, matches=s.matches, wins=s.wins, win_rate=s.win_rate)
            for s in form.by_surface.values()
        ],
        streak_type=form.streak_type,
        streak_count=form.streak_count,
        days_since_last_match=form.days_since_last_match,
        matches_last_30_days=form.matches_last_30_days,
    )


@app.get("/players/{player_id}/rankings", response_model=list[RankingSnapshotOut])
def player_rankings(
    player_id: int,
    db: Session = Depends(get_db),
    tour: str | None = Query(None, description="atp | wta - omettre pour les deux"),
    limit: int = Query(52, le=500, description="Nombre de snapshots, les plus recents d'abord"),
):
    """Historique de classement du joueur. precision='weekly' = capture par nos soins
    (fiable, disponible depuis le 2026-08-08), 'season_approx' = reconstitue depuis le
    fournisseur pour les periodes anterieures (pas encore implemente - voir modele)."""
    player = db.query(Player).filter(Player.id == player_id).one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="Joueur introuvable")

    query = db.query(RankingSnapshot).filter(RankingSnapshot.player_id == player_id)
    if tour:
        query = query.filter(RankingSnapshot.tour == tour)
    return query.order_by(RankingSnapshot.snapshot_date.desc()).limit(limit).all()


@app.get("/players/{player_id}/h2h/{other_player_id}", response_model=H2HOut)
def head_to_head(player_id: int, other_player_id: int, db: Session = Depends(get_db)):
    """Le H2H n'est jamais stocke: toujours recalcule depuis matches, qui est la seule
    source de verite (voir docstring de models.py)."""
    player1 = db.query(Player).filter(Player.id == player_id).one_or_none()
    player2 = db.query(Player).filter(Player.id == other_player_id).one_or_none()
    if not player1 or not player2:
        raise HTTPException(status_code=404, detail="Joueur introuvable")

    match_ids = [
        row[0]
        for row in db.query(Match.id)
        .filter(
            or_(
                (Match.player1_id == player_id) & (Match.player2_id == other_player_id),
                (Match.player1_id == other_player_id) & (Match.player2_id == player_id),
            )
        )
        .order_by(Match.scheduled_at.desc())
        .all()
    ]
    matches = []
    if match_ids:
        by_id = {
            m.id: m
            for m in db.query(Match)
            .options(joinedload(Match.tournament), joinedload(Match.player1), joinedload(Match.player2))
            .filter(Match.id.in_(match_ids))
            .all()
        }
        matches = [by_id[i] for i in match_ids if i in by_id]

    return H2HOut(
        player1=player1,
        player2=player2,
        player1_wins=sum(1 for m in matches if m.winner_id == player_id),
        player2_wins=sum(1 for m in matches if m.winner_id == other_player_id),
        matches=matches,
    )
