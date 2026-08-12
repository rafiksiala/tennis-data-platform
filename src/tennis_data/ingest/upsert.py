"""
Upsert idempotent: transforme un enregistrement brut API-Tennis en lignes dans notre
modele normalise. Rejouable sans creer de doublons (cle = external_id du fournisseur).
"""

from datetime import datetime

from sqlalchemy.orm import Session

from tennis_data.ingest.mapping import (
    SOURCE,
    normalize_round,
    normalize_stat_name,
    normalize_status,
    parse_score_component,
    parse_stat_value,
)
from tennis_data.models import (
    Match,
    MatchExternalId,
    MatchSet,
    MatchStatistic,
    Player,
    PlayerExternalId,
    Tournament,
    TournamentExternalId,
)

TOUR_LABELS = {
    "Atp Singles": "atp",
    "Wta Singles": "wta",
    "Challenger Men Singles": "challenger_men",
    "Challenger Women Singles": "challenger_women",
    "Itf Men Singles": "itf_men",
    "Itf Women Singles": "itf_women",
}


def get_or_create_player(session: Session, external_id: int | str, name: str | None) -> Player:
    external_id = str(external_id)
    link = (
        session.query(PlayerExternalId)
        .filter_by(source=SOURCE, external_id=external_id)
        .one_or_none()
    )
    if link:
        if name and link.player.full_name != name:
            link.player.full_name = name
        return link.player

    player = Player(full_name=name or f"unknown_{external_id}")
    session.add(player)
    session.flush()  # pour obtenir player.id
    session.add(PlayerExternalId(player_id=player.id, source=SOURCE, external_id=external_id))
    return player


def get_or_create_tournament(
    session: Session,
    tournament_key: int | str,
    season: int,
    name: str,
    tour: str,
    surface: str | None = None,
) -> Tournament:
    """cle d'upsert composite {tournament_key}_{season}: voir commentaire sur
    Tournament.external_series_key dans models.py pour le raisonnement."""
    composite_id = f"{tournament_key}_{season}"
    link = (
        session.query(TournamentExternalId)
        .filter_by(source=SOURCE, external_id=composite_id)
        .one_or_none()
    )
    if link:
        tournament = link.tournament
        if surface and not tournament.surface:
            tournament.surface = surface
        return tournament

    tournament = Tournament(
        name=name,
        tour=tour,
        surface=surface,
        season=season,
        external_series_key=str(tournament_key),
    )
    session.add(tournament)
    session.flush()
    session.add(TournamentExternalId(tournament_id=tournament.id, source=SOURCE, external_id=composite_id))
    return tournament


def upsert_match_from_fixture(
    session: Session,
    fixture: dict,
    tour_surface_lookup: dict[str, str] | None = None,
) -> Match | None:
    """fixture: un element de get_fixtures()['result']. Retourne le Match upserte,
    ou None si l'enregistrement est incomplet (ex: joueur TBD)."""
    tour_surface_lookup = tour_surface_lookup or {}

    event_key = fixture.get("event_key")
    if event_key is None:
        return None

    tour = TOUR_LABELS.get(fixture.get("event_type_type"), fixture.get("event_type_type", "unknown").lower())
    tournament_key = fixture.get("tournament_key")
    season = int(fixture.get("tournament_season") or 0) or datetime.now().year
    surface = tour_surface_lookup.get(str(tournament_key))
    tournament = get_or_create_tournament(
        session,
        tournament_key=tournament_key,
        season=season,
        name=(fixture.get("tournament_name") or "").strip(),
        tour=tour,
        surface=surface,
    )

    p1_key, p2_key = fixture.get("first_player_key"), fixture.get("second_player_key")
    player1 = get_or_create_player(session, p1_key, fixture.get("event_first_player")) if p1_key else None
    player2 = get_or_create_player(session, p2_key, fixture.get("event_second_player")) if p2_key else None

    winner = None
    event_winner = fixture.get("event_winner")
    if event_winner == "First Player":
        winner = player1
    elif event_winner == "Second Player":
        winner = player2

    status, status_raw = normalize_status(fixture.get("event_status"))
    round_code, round_raw = normalize_round(fixture.get("tournament_round"))

    scheduled_at = None
    if fixture.get("event_date"):
        time_part = fixture.get("event_time") or "00:00"
        try:
            scheduled_at = datetime.strptime(f"{fixture['event_date']} {time_part}", "%Y-%m-%d %H:%M")
        except ValueError:
            scheduled_at = None

    is_qualification = str(fixture.get("event_qualification", "")).strip().lower() == "true"

    link = (
        session.query(MatchExternalId)
        .filter_by(source=SOURCE, external_id=str(event_key))
        .one_or_none()
    )
    match = link.match if link else Match(tournament_id=tournament.id)

    match.tournament_id = tournament.id
    match.round_raw = round_raw
    match.round_code = round_code
    match.player1_id = player1.id if player1 else None
    match.player2_id = player2.id if player2 else None
    match.winner_id = winner.id if winner else None
    match.status = status
    match.status_raw = status_raw
    match.is_qualification = is_qualification
    match.scheduled_at = scheduled_at
    match.score_raw = fixture.get("event_final_result")
    match.points_raw = {"pointbypoint": fixture.get("pointbypoint")} if fixture.get("pointbypoint") else None
    match.last_synced_at = datetime.utcnow()

    if not link:
        session.add(match)
        session.flush()
        session.add(MatchExternalId(match_id=match.id, source=SOURCE, external_id=str(event_key)))

    player_id_by_external_key = {}
    if p1_key and player1:
        player_id_by_external_key[str(p1_key)] = player1.id
    if p2_key and player2:
        player_id_by_external_key[str(p2_key)] = player2.id

    _upsert_sets(session, match, fixture.get("scores") or [])
    _upsert_statistics(session, match, fixture.get("statistics") or [], player_id_by_external_key)

    return match


def _upsert_sets(session: Session, match: Match, scores: list[dict]) -> None:
    existing = {s.set_number: s for s in match.sets}
    for raw_set in scores:
        try:
            set_number = int(raw_set.get("score_set"))
        except (TypeError, ValueError):
            continue
        g1, tb1 = parse_score_component(raw_set.get("score_first"))
        g2, tb2 = parse_score_component(raw_set.get("score_second"))
        row = existing.get(set_number)
        if row is None:
            row = MatchSet(match_id=match.id, set_number=set_number)
            session.add(row)
            existing[set_number] = row  # meme raison que dans _upsert_statistics: eviter un double INSERT
        row.player1_games = g1
        row.player2_games = g2
        row.tiebreak_player1_points = tb1
        row.tiebreak_player2_points = tb2


def _upsert_statistics(
    session: Session, match: Match, statistics: list[dict], player_id_by_external_key: dict[str, int]
) -> None:
    if not statistics:
        return
    existing = {
        (s.player_id, s.stat_period, s.stat_name): s
        for s in session.query(MatchStatistic).filter_by(match_id=match.id).all()
    }
    for raw_stat in statistics:
        player_id = player_id_by_external_key.get(str(raw_stat.get("player_key")))
        if not player_id:
            continue
        stat_period = str(raw_stat.get("stat_period") or "match")
        stat_name = normalize_stat_name(raw_stat.get("stat_name") or "")
        key = (player_id, stat_period, stat_name)
        row = existing.get(key)
        if row is None:
            row = MatchStatistic(
                match_id=match.id,
                player_id=player_id,
                stat_period=stat_period,
                stat_name=stat_name,
            )
            session.add(row)
            existing[key] = row  # sinon un doublon plus loin dans la meme liste retente un INSERT
        row.stat_value = parse_stat_value(raw_stat.get("stat_value"))
        row.stat_won = raw_stat.get("stat_won")
        row.stat_total = raw_stat.get("stat_total")
        row.raw_stat_name = raw_stat.get("stat_name")
