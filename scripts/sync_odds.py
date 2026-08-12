"""
Capture des cotes des matchs A VENIR (et recemment termines), a lancer chaque jour.

C'est la piece qui garantit qu'on ne perd plus jamais de cotes: contrairement au
backfill retroactif (une seule valeur par match, sans horodatage fiable), ce script
tourne chaque jour et cree une NOUVELLE ligne odds_snapshots a chaque execution tant
que le match n'a pas eu lieu -> avec le temps, on accumule une vraie serie temporelle
(cote d'ouverture, evolution, cloture juste avant/apres le match), avec un captured_at
digne de confiance (contrairement aux cotes backfillees).

Fenetre: matchs entre J-2 (pour capturer la cloture des matchs tout juste termines)
et J+7 (matchs a venir). Un seul snapshot par match et par jour (si le job est relance
le meme jour, il ne recree pas de doublon).

Usage:
    python scripts/sync_odds.py
    python scripts/sync_odds.py --tours atp,wta --lookback-days 2 --lookahead-days 7
"""

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tennis_data.db import get_session
from tennis_data.ingest.mapping import SOURCE, flatten_odds
from tennis_data.models import IngestRun, Match, MatchExternalId, OddsSnapshot, Tournament
from tennis_data.providers.api_tennis import ApiTennisClient, ApiTennisQuotaExceeded

CHUNK_SIZE = 50


def _log_run_safely(**kwargs) -> None:
    try:
        with get_session() as session:
            session.add(IngestRun(**kwargs))
    except Exception as log_exc:  # noqa: BLE001
        print(f"    (impossible d'ecrire l'IngestRun d'echec: {log_exc})")


def fetch_candidates(session, tours: list[str], window_start, window_end) -> list[tuple[int, int]]:
    today = datetime.now(timezone.utc).date()
    rows = (
        session.query(Match.id, MatchExternalId.external_id)
        .join(Tournament, Match.tournament_id == Tournament.id)
        .join(MatchExternalId, MatchExternalId.match_id == Match.id)
        .filter(Tournament.tour.in_(tours))
        .filter(Match.status.in_(["scheduled", "live", "finished"]))
        .filter(Match.scheduled_at >= window_start)
        .filter(Match.scheduled_at <= window_end)
        .filter(MatchExternalId.source == SOURCE)
        .filter(
            ~Match.id.in_(
                session.query(OddsSnapshot.match_id).filter(
                    OddsSnapshot.is_retroactive.is_(False),
                    OddsSnapshot.captured_at >= today,
                )
            )
        )
        .all()
    )
    return [(r[0], r[1]) for r in rows]


def process_chunk(client: ApiTennisClient, chunk: list[tuple[int, int]]) -> dict:
    found, not_found, calls = 0, 0, 0
    now = datetime.now(timezone.utc)
    with get_session() as session:
        run = IngestRun(job_name="sync_odds")
        session.add(run)
        session.flush()

        for match_id, external_id in chunk:
            odds_dict = client.get_odds(int(external_id))
            calls += 1
            if odds_dict:
                for row in flatten_odds(odds_dict):
                    session.add(
                        OddsSnapshot(
                            match_id=match_id,
                            bookmaker=row["bookmaker"],
                            market=row["market"],
                            selection=row["selection"],
                            odd_value=row["value"],
                            captured_at=now,
                            is_retroactive=False,
                            source=SOURCE,
                        )
                    )
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
    parser.add_argument("--lookback-days", type=int, default=2)
    parser.add_argument("--lookahead-days", type=int, default=7)
    args = parser.parse_args()
    tours = args.tours.split(",")

    client = ApiTennisClient()
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=args.lookback_days)
    window_end = now + timedelta(days=args.lookahead_days)

    with get_session() as session:
        candidates = fetch_candidates(session, tours, window_start, window_end)
    print(f"{len(candidates)} matchs a capturer (fenetre {window_start.date()} -> {window_end.date()})")

    total_found, total_not_found, total_calls = 0, 0, 0
    for i in range(0, len(candidates), CHUNK_SIZE):
        chunk = candidates[i : i + CHUNK_SIZE]
        try:
            result = process_chunk(client, chunk)
        except ApiTennisQuotaExceeded as exc:
            print(f"\nQUOTA API EPUISE a {i}/{len(candidates)} matchs traites ({exc})")
            print("Arret propre. Le prochain run planifie reprendra le reste.")
            break
        except Exception as exc:  # noqa: BLE001
            print(f"  lot {i}-{i+len(chunk)}: ECHEC ({exc}), on continue sur le suivant")
            _log_run_safely(
                job_name="sync_odds",
                status="failed",
                finished_at=datetime.now(timezone.utc),
                error_message=str(exc)[:1000],
            )
            continue
        total_found += result["found"]
        total_not_found += result["not_found"]
        total_calls += result["calls"]

    print(f"Termine: {total_found} matchs avec cotes capturees, {total_not_found} sans cotes, "
          f"{total_calls} appels API")


if __name__ == "__main__":
    main()
