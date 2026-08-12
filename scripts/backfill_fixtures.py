"""
Backfill historique des matchs (tournois/joueurs/matchs/sets/statistiques).

Profondeur choisie: 2021-01-01 -> aujourd'hui, sur la base des tests reels du
2026-08-08 (voir conversation / tennis-data-research) qui montrent que les fixtures
ATP Singles sont vides en 2020 et partielles en 2021. Meme date de depart appliquee
aux 4 tours suivis (ATP/WTA/Challenger H/Challenger F) par simplification: si un tour
a en realite moins de profondeur, les appels sur les annees vides ne renverront
simplement rien (cout: quelques dizaines d'appels perdus, negligeable).

Usage:
    python scripts/backfill_fixtures.py                     # les 4 tours, 2021 -> aujourd'hui
    python scripts/backfill_fixtures.py --tours atp_singles  # un seul tour
    python scripts/backfill_fixtures.py --start 2023-01-01   # reprise partielle
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tennis_data.db import get_session
from tennis_data.ingest.bulk_upsert import BulkCache, bulk_upsert_fixtures
from tennis_data.ingest.enrich import build_surface_lookup
from tennis_data.models import IngestRun
from tennis_data.providers.api_tennis import EVENT_TYPES, ApiTennisClient, ApiTennisQuotaExceeded

DEFAULT_START = "2021-01-01"


MAX_ATTEMPTS = 3


def _already_done(tour_key: str, year: int) -> bool:
    """Permet de relancer le script sans refaire le travail deja committe avec succes."""
    with get_session() as session:
        existing = (
            session.query(IngestRun)
            .filter_by(job_name=f"backfill_fixtures:{tour_key}:{year}", status="success")
            .first()
        )
        return existing is not None


def _log_run_safely(**kwargs) -> None:
    """Ecrit un IngestRun sans jamais faire planter l'appelant (utile quand la panne
    initiale est elle-meme un probleme reseau: on ne veut pas perdre le programme
    entier juste parce que le LOG de l'echec n'a pas pu s'ecrire non plus)."""
    try:
        with get_session() as session:
            session.add(IngestRun(**kwargs))
    except Exception as log_exc:  # noqa: BLE001
        print(f"    (impossible d'ecrire l'IngestRun d'echec: {log_exc})")


def backfill_tour(client: ApiTennisClient, tour_key: str, start: str, end: str, surface_lookup: dict) -> dict:
    """Une session (donc une transaction) PAR ANNEE: si une annee echoue (donnee
    inattendue non geree, ou coupure reseau transitoire), les annees precedentes deja
    committees ne sont pas perdues, et le backfill continue sur les annees suivantes
    plutot que d'abandonner tout le tour. Resumable: une annee deja en succes dans
    ingest_runs est sautee (voir _already_done)."""
    event_type_key = EVENT_TYPES[tour_key]
    stats = {"matches_seen": 0, "api_calls": 0, "years_failed": []}

    for year in range(int(start[:4]), int(end[:4]) + 1):
        if _already_done(tour_key, year):
            print(f"  [{tour_key}] {year}: deja fait, on saute")
            continue

        year_start = f"{year}-01-01" if year > int(start[:4]) else start
        year_end = f"{year}-12-31" if year < int(end[:4]) else end
        n_calls = -(-((datetime.strptime(year_end, "%Y-%m-%d") - datetime.strptime(year_start, "%Y-%m-%d")).days + 1) // 7)

        last_exc = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                fixtures = client.get_fixtures_range(year_start, year_end, event_type_key=event_type_key)
                print(f"  [{tour_key}] {year}: {len(fixtures)} matchs recuperes (tentative {attempt})")
                with get_session() as session:
                    run = IngestRun(job_name=f"backfill_fixtures:{tour_key}:{year}")
                    session.add(run)
                    session.flush()
                    # cache reconstruit a chaque tentative depuis LA MEME session: si une
                    # tentative precedente a echoue (rollback), on ne doit surtout pas
                    # reutiliser un cache qui pointerait vers des lignes annulees.
                    cache = BulkCache(session)
                    created = bulk_upsert_fixtures(session, fixtures, cache, surface_lookup)
                    run.status = "success"
                    run.finished_at = datetime.now(timezone.utc)
                    run.rows_inserted = created
                    run.api_calls_made = n_calls
                stats["matches_seen"] += len(fixtures)
                stats["api_calls"] += n_calls
                last_exc = None
                break
            except ApiTennisQuotaExceeded:
                raise  # inutile de retenter ou de continuer sur les autres annees/tours
            except Exception as exc:  # noqa: BLE001 - on retente, et on continue quoi qu'il arrive
                last_exc = exc
                print(f"  [{tour_key}] {year}: tentative {attempt}/{MAX_ATTEMPTS} echouee ({exc})")
                if attempt < MAX_ATTEMPTS:
                    time.sleep(10 * attempt)  # 10s, 20s: laisse le temps a un blip reseau de se resorber

        if last_exc is not None:
            print(f"  [{tour_key}] {year}: ECHEC definitif apres {MAX_ATTEMPTS} tentatives - annee ignoree, on continue")
            stats["years_failed"].append(year)
            _log_run_safely(
                job_name=f"backfill_fixtures:{tour_key}:{year}",
                status="failed",
                finished_at=datetime.now(timezone.utc),
                error_message=str(last_exc)[:1000],
                api_calls_made=n_calls,
            )
        time.sleep(0.3)

    return stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tours", default="atp_singles,wta_singles,challenger_men_singles,challenger_women_singles")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=str(datetime.now().date()))
    args = parser.parse_args()

    client = ApiTennisClient()
    surface_lookup = build_surface_lookup(client)

    for tour_key in args.tours.split(","):
        print(f"\n=== Backfill {tour_key} ({args.start} -> {args.end}) ===")
        try:
            stats = backfill_tour(client, tour_key, args.start, args.end, surface_lookup)
        except ApiTennisQuotaExceeded as exc:
            print(f"\nQUOTA API EPUISE ({exc}). Arret propre.")
            print("Relance le script plus tard (apres reset du quota, ou plan superieur):"
                  " il reprendra automatiquement la ou il s'est arrete.")
            return
        print(f"  Termine: {stats['matches_seen']} matchs, ~{stats['api_calls']} appels API")
        if stats["years_failed"]:
            print(f"  ATTENTION: annees en echec pour {tour_key}: {stats['years_failed']} (voir ingest_runs pour le detail)")


if __name__ == "__main__":
    main()
