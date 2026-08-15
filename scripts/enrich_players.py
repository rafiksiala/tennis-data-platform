"""
Enrichit players.country_code et players.birth_date via get_players (1 appel API par
joueur, pas de recuperation en masse possible - confirme par test le 2026-08-08).

Priorise les joueurs "actifs" (ont joue recemment) plutot que les ~7000 joueurs jamais
revus depuis 2021: sur ~3700 joueurs actifs (24 derniers mois), ~1900 sont ATP/WTA
(traites en premier, forte valeur produit) et le reste Challenger (volume/valeur plus
faible, traite ensuite).

Note sur le nom du champ: malgre "country_code", on stocke le nom de pays BRUT tel que
renvoye par le fournisseur (ex: "Spain", pas "ES") - pas de code ISO disponible cote
API. Le mapping nom -> drapeau se fait cote frontend (voir src/lib/countries.ts).

Idempotent: ne traite que les joueurs sans country_code NI birth_date deja rempli,
donc relancer ce script ne re-consomme pas de quota sur ce qui est deja fait.

Usage:
    python scripts/enrich_players.py                          # ATP/WTA actifs (24 mois)
    python scripts/enrich_players.py --tours challenger_men,challenger_women
    python scripts/enrich_players.py --months 12 --limit 500   # tester sur un sous-ensemble
"""

import argparse
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tennis_data.db import get_session
from tennis_data.ingest.mapping import SOURCE
from tennis_data.models import IngestRun, Match, Player, PlayerExternalId, Tournament
from tennis_data.providers.api_tennis import ApiTennisClient, ApiTennisQuotaExceeded

CHUNK_SIZE = 50


def parse_bday(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw.strip(), "%d.%m.%Y").date()
    except ValueError:
        return None


def fetch_target_player_ids(session, tours: list[str], months: int, limit: int | None) -> list[int]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30)
    q = (
        session.query(Player.id)
        .join(
            Match,
            (Match.player1_id == Player.id) | (Match.player2_id == Player.id),
        )
        .join(Tournament, Tournament.id == Match.tournament_id)
        .filter(Tournament.tour.in_(tours))
        .filter(Match.scheduled_at >= cutoff)
        .filter(Player.country_code.is_(None), Player.birth_date.is_(None))
        .distinct()
    )
    if limit:
        q = q.limit(limit)
    return [row[0] for row in q.all()]


def process_chunk(client: ApiTennisClient, player_ids: list[int]) -> dict:
    found, not_found, calls = 0, 0, 0
    with get_session() as session:
        run = IngestRun(job_name="enrich_players")
        session.add(run)
        session.flush()

        ext_by_player = {
            row.player_id: row.external_id
            for row in session.query(PlayerExternalId)
            .filter(PlayerExternalId.source == SOURCE, PlayerExternalId.player_id.in_(player_ids))
            .all()
        }

        for player_id in player_ids:
            external_id = ext_by_player.get(player_id)
            if not external_id:
                continue
            result = client.get_players(player_key=int(external_id))
            calls += 1
            if result:
                info = result[0]
                player = session.query(Player).filter(Player.id == player_id).one()
                player.country_code = info.get("player_country") or None
                player.birth_date = parse_bday(info.get("player_bday"))
                found += 1
            else:
                not_found += 1
            time.sleep(0.2)

        run.status = "success"
        run.finished_at = datetime.now(timezone.utc)
        run.rows_inserted = found
        run.api_calls_made = calls

    return {"found": found, "not_found": not_found, "calls": calls}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tours", default="atp,wta")
    parser.add_argument("--months", type=int, default=24)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    tours = args.tours.split(",")

    client = ApiTennisClient()

    with get_session() as session:
        target_ids = fetch_target_player_ids(session, tours, args.months, args.limit)
    print(f"{len(target_ids)} joueurs a enrichir (tours={tours}, {args.months} derniers mois)")

    total_found, total_not_found, total_calls = 0, 0, 0
    for i in range(0, len(target_ids), CHUNK_SIZE):
        chunk = target_ids[i : i + CHUNK_SIZE]
        try:
            result = process_chunk(client, chunk)
        except ApiTennisQuotaExceeded as exc:
            print(f"\nQUOTA API EPUISE a {i}/{len(target_ids)} joueurs traites ({exc})")
            print("Arret propre. Relance le script plus tard: il reprendra sur les joueurs restants.")
            break
        except Exception as exc:  # noqa: BLE001
            print(f"  lot {i}-{i+len(chunk)}: ECHEC ({exc}), on continue sur le suivant")
            continue
        total_found += result["found"]
        total_not_found += result["not_found"]
        total_calls += result["calls"]
        print(f"  ... {i + len(chunk)}/{len(target_ids)} traites (trouve={total_found}, absent={total_not_found})")

    print(f"Termine: {total_found} joueurs enrichis, {total_not_found} sans reponse, {total_calls} appels API")


if __name__ == "__main__":
    main()
