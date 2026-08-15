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

from tennis_data.api.deps import get_db
from tennis_data.api.schemas import MatchDetailOut, MatchListOut, TournamentOut
from tennis_data.models import Match, MatchStatistic, OddsSnapshot, Player, Tournament

app = FastAPI(title="Tennis Data API", version="0.1.0")

# CORS ouvert en dev - a restreindre a l'origine du frontend une fois deployee
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    # correspondent tous les deux). Sans q, l'appliquer quand meme forcait Postgres a
    # trier/dedupliquer toute la table avant de limiter -> timeout sur 100k+ matchs
    # (trouve par test le 2026-08-13 sur le deploiement Render).
    total = query.distinct(Match.id).count() if q else query.count()
    query = query.options(
        joinedload(Match.tournament),
        joinedload(Match.player1),
        joinedload(Match.player2),
    ).order_by(Match.scheduled_at.desc().nullslast())
    if q:
        query = query.distinct()
    matches = query.offset(offset).limit(limit).all()

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
