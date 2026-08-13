"""
Upsert en masse pour le backfill: le module upsert.py fait une poignee de requetes
par match (recherche + creation), ce qui est simple et correct mais devient trop lent
sur un gros volume a cause de la latence reseau vers la base (chaque aller-retour vers
Render coute ~100-300ms, et un backfill de plusieurs annees represente des dizaines de
milliers de matchs -> plusieurs jours a ce rythme, confirme empiriquement le 2026-08-09).

Principe: charger une fois en memoire les correspondances externe->interne deja connues
(BulkCache), puis ne faire qu'une poignee d'aller-retours PAR LOT de fixtures (pas par
match): un flush pour les nouveaux joueurs/tournois, un flush pour les nouveaux matchs,
puis les sets/stats sont ajoutes sans requete supplementaire (on sait que ce sont des
matchs tout neufs dans ce lot, donc pas de verification de doublon necessaire).

Limitation assumee: un match DEJA present en base (cache.match_ids) est ignore par ce
module (pas de mise a jour). C'est correct pour un backfill historique (les vieux matchs
ne changent plus) mais PAS adapte a la synchro quotidienne, qui doit gerer les
corrections de matchs recents -> daily_sync.py continue donc a utiliser upsert.py.
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
from tennis_data.ingest.upsert import TOUR_LABELS
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

BATCH_SIZE = 150  # nombre de matchs traites entre deux flush, pour eviter un flush demesure


class BulkCache:
    """Charge une fois les correspondances externe->interne existantes, les garde a
    jour en memoire ensuite. Valable pour un run mono-processus (le backfill)."""

    def __init__(self, session: Session):
        self.session = session
        self.player_ids = {r.external_id: r.player_id for r in session.query(PlayerExternalId).filter_by(source=SOURCE)}
        self.tournament_ids = {
            r.external_id: r.tournament_id for r in session.query(TournamentExternalId).filter_by(source=SOURCE)
        }
        self.match_ids = {r.external_id: r.match_id for r in session.query(MatchExternalId).filter_by(source=SOURCE)}
        print(
            f"  [cache] {len(self.player_ids)} joueurs, {len(self.tournament_ids)} tournois, "
            f"{len(self.match_ids)} matchs deja connus"
        )


def bulk_upsert_fixtures(session: Session, fixtures: list[dict], cache: BulkCache, tour_surface_lookup: dict) -> int:
    """Traite `fixtures` par lots de BATCH_SIZE. Retourne le nombre de matchs crees
    (les matchs deja connus dans le cache sont ignores, voir docstring du module)."""
    total_created = 0
    for i in range(0, len(fixtures), BATCH_SIZE):
        batch = fixtures[i : i + BATCH_SIZE]
        total_created += _process_batch(session, batch, cache, tour_surface_lookup)
        session.flush()
    return total_created


def _process_batch(session: Session, fixtures: list[dict], cache: BulkCache, tour_surface_lookup: dict) -> int:
    # --- phase 1: joueurs + tournois manquants ---
    new_players: dict[str, Player] = {}
    new_tournaments: dict[str, Tournament] = {}

    for fx in fixtures:
        for key, name in (
            (fx.get("first_player_key"), fx.get("event_first_player")),
            (fx.get("second_player_key"), fx.get("event_second_player")),
        ):
            if key is None:
                continue
            key = str(key)
            if key not in cache.player_ids and key not in new_players:
                new_players[key] = Player(full_name=name or f"unknown_{key}")

        tkey = fx.get("tournament_key")
        season = int(fx.get("tournament_season") or 0) or datetime.now().year
        composite = f"{tkey}_{season}"
        if composite not in cache.tournament_ids and composite not in new_tournaments:
            tour = TOUR_LABELS.get(fx.get("event_type_type"), (fx.get("event_type_type") or "unknown").lower())
            surface = tour_surface_lookup.get(str(tkey))
            new_tournaments[composite] = Tournament(
                name=(fx.get("tournament_name") or "").strip(),
                tour=tour,
                surface=surface,
                season=season,
                external_series_key=str(tkey),
            )

    for player in new_players.values():
        session.add(player)
    for tournament in new_tournaments.values():
        session.add(tournament)
    if new_players or new_tournaments:
        session.flush()

    for ext_id, player in new_players.items():
        cache.player_ids[ext_id] = player.id
        session.add(PlayerExternalId(player_id=player.id, source=SOURCE, external_id=ext_id))
    for composite, tournament in new_tournaments.items():
        cache.tournament_ids[composite] = tournament.id
        session.add(TournamentExternalId(tournament_id=tournament.id, source=SOURCE, external_id=composite))

    # --- phase 2: matchs manquants ---
    new_matches: dict[str, Match] = {}
    fixtures_by_key: dict[str, dict] = {}

    for fx in fixtures:
        event_key = fx.get("event_key")
        if event_key is None:
            continue
        event_key = str(event_key)
        fixtures_by_key[event_key] = fx
        if event_key in cache.match_ids or event_key in new_matches:
            continue

        tkey = fx.get("tournament_key")
        season = int(fx.get("tournament_season") or 0) or datetime.now().year
        composite = f"{tkey}_{season}"
        tournament_id = cache.tournament_ids.get(composite)

        p1_key, p2_key = fx.get("first_player_key"), fx.get("second_player_key")
        player1_id = cache.player_ids.get(str(p1_key)) if p1_key else None
        player2_id = cache.player_ids.get(str(p2_key)) if p2_key else None

        event_winner = fx.get("event_winner")
        winner_id = None
        if event_winner == "First Player":
            winner_id = player1_id
        elif event_winner == "Second Player":
            winner_id = player2_id

        status, status_raw = normalize_status(fx.get("event_status"))
        is_qualification = str(fx.get("event_qualification", "")).strip().lower() == "true"
        round_code, round_raw = normalize_round(fx.get("tournament_round"), is_qualification)

        scheduled_at = None
        if fx.get("event_date"):
            try:
                scheduled_at = datetime.strptime(
                    f"{fx['event_date']} {fx.get('event_time') or '00:00'}", "%Y-%m-%d %H:%M"
                )
            except ValueError:
                scheduled_at = None

        match = Match(
            tournament_id=tournament_id,
            round_raw=round_raw,
            round_code=round_code,
            player1_id=player1_id,
            player2_id=player2_id,
            winner_id=winner_id,
            status=status,
            status_raw=status_raw,
            is_qualification=is_qualification,
            scheduled_at=scheduled_at,
            score_raw=fx.get("event_final_result"),
            points_raw={"pointbypoint": fx["pointbypoint"]} if fx.get("pointbypoint") else None,
            last_synced_at=datetime.utcnow(),
        )
        session.add(match)
        new_matches[event_key] = match

    if new_matches:
        session.flush()

    for event_key, match in new_matches.items():
        cache.match_ids[event_key] = match.id
        session.add(MatchExternalId(match_id=match.id, source=SOURCE, external_id=event_key))

    # --- phase 3: sets + stats (uniquement pour les matchs tout neufs de ce lot) ---
    for event_key, match in new_matches.items():
        fx = fixtures_by_key[event_key]
        _add_sets(session, match.id, fx.get("scores") or [])

        p1_key, p2_key = fx.get("first_player_key"), fx.get("second_player_key")
        player_id_by_external_key = {}
        if p1_key:
            player_id_by_external_key[str(p1_key)] = cache.player_ids.get(str(p1_key))
        if p2_key:
            player_id_by_external_key[str(p2_key)] = cache.player_ids.get(str(p2_key))
        _add_statistics(session, match.id, fx.get("statistics") or [], player_id_by_external_key)

    return len(new_matches)


def _add_sets(session: Session, match_id: int, scores: list[dict]) -> None:
    seen = set()
    for raw_set in scores:
        try:
            set_number = int(raw_set.get("score_set"))
        except (TypeError, ValueError):
            continue
        if set_number in seen:  # doublon observe dans certaines reponses le 2026-08-09
            continue
        seen.add(set_number)
        g1, tb1 = parse_score_component(raw_set.get("score_first"))
        g2, tb2 = parse_score_component(raw_set.get("score_second"))
        session.add(
            MatchSet(
                match_id=match_id,
                set_number=set_number,
                player1_games=g1,
                player2_games=g2,
                tiebreak_player1_points=tb1,
                tiebreak_player2_points=tb2,
            )
        )


def _add_statistics(
    session: Session, match_id: int, statistics: list[dict], player_id_by_external_key: dict[str, int]
) -> None:
    seen = set()
    for raw_stat in statistics:
        player_id = player_id_by_external_key.get(str(raw_stat.get("player_key")))
        if not player_id:
            continue
        stat_period = str(raw_stat.get("stat_period") or "match")
        stat_name = normalize_stat_name(raw_stat.get("stat_name") or "")
        key = (player_id, stat_period, stat_name)
        if key in seen:  # meme cas de doublon que pour les sets
            continue
        seen.add(key)
        session.add(
            MatchStatistic(
                match_id=match_id,
                player_id=player_id,
                stat_period=stat_period,
                stat_name=stat_name,
                stat_value=parse_stat_value(raw_stat.get("stat_value")),
                stat_won=raw_stat.get("stat_won"),
                stat_total=raw_stat.get("stat_total"),
                raw_stat_name=raw_stat.get("stat_name"),
            )
        )
