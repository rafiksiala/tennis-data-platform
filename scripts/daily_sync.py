"""
Synchronisation quotidienne: nouveaux matchs, changements de statut, corrections de score.

Fenetre volontairement large en arriere (14 jours) pour rattraper d'eventuelles
corrections tardives (score corrige, retirement reclasse, stats ajoutees apres coup),
et quelques jours en avant pour recuperer le calendrier a venir.

A planifier quotidiennement (ex: tous les jours a 6h du matin) via le planificateur
de taches. Idempotent: peut etre relance sans risque en cas d'echec partiel.

Usage:
    python scripts/daily_sync.py
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tennis_data.db import get_session
from tennis_data.ingest.enrich import build_surface_lookup
from tennis_data.ingest.maintenance import reclassify_stale_qualifying_finals
from tennis_data.ingest.upsert import upsert_match_from_fixture
from tennis_data.models import IngestRun
from tennis_data.providers.api_tennis import EVENT_TYPES, ApiTennisClient, ApiTennisQuotaExceeded

TOURS = ["atp_singles", "wta_singles", "challenger_men_singles", "challenger_women_singles"]
LOOKBACK_DAYS = 14
LOOKAHEAD_DAYS = 5


def _log_run_safely(**kwargs) -> None:
    try:
        with get_session() as session:
            session.add(IngestRun(**kwargs))
    except Exception as log_exc:  # noqa: BLE001
        print(f"    (impossible d'ecrire l'IngestRun: {log_exc})")


def main():
    client = ApiTennisClient()

    try:
        surface_lookup = build_surface_lookup(client)
    except ApiTennisQuotaExceeded as exc:
        print(f"QUOTA API EPUISE avant meme de demarrer ({exc}). Le prochain run planifie reprendra normalement.")
        _log_run_safely(job_name="daily_sync", status="failed", finished_at=datetime.now(timezone.utc),
                         error_message=str(exc)[:1000])
        return

    date_start = str(datetime.now().date() - timedelta(days=LOOKBACK_DAYS))
    date_stop = str(datetime.now().date() + timedelta(days=LOOKAHEAD_DAYS))

    total, calls = 0, 0
    for tour_key in TOURS:
        try:
            with get_session() as session:
                run = IngestRun(job_name=f"daily_sync:{tour_key}")
                session.add(run)
                session.flush()

                fixtures = client.get_fixtures_range(date_start, date_stop, event_type_key=EVENT_TYPES[tour_key])
                n_calls = -(-((datetime.strptime(date_stop, "%Y-%m-%d") - datetime.strptime(date_start, "%Y-%m-%d")).days + 1) // 7)
                print(f"[{tour_key}] {len(fixtures)} matchs sur la fenetre {date_start} -> {date_stop}")
                for fx in fixtures:
                    upsert_match_from_fixture(session, fx, tour_surface_lookup=surface_lookup)
                session.flush()

                run.status = "success"
                run.finished_at = datetime.now(timezone.utc)
                run.rows_inserted = len(fixtures)
                run.api_calls_made = n_calls
            total += len(fixtures)
            calls += n_calls
        except ApiTennisQuotaExceeded as exc:
            print(f"QUOTA API EPUISE sur {tour_key} ({exc}). Arret propre, le prochain run planifie reprendra.")
            break
        except Exception as exc:  # noqa: BLE001 - un tour en echec ne doit pas bloquer les autres
            print(f"[{tour_key}] ECHEC ({exc}), on continue sur le suivant")
            _log_run_safely(job_name=f"daily_sync:{tour_key}", status="failed",
                             finished_at=datetime.now(timezone.utc), error_message=str(exc)[:1000])
        time.sleep(0.3)

    try:
        with get_session() as session:
            n_reclassified = reclassify_stale_qualifying_finals(session)
        if n_reclassified:
            print(f"  {n_reclassified} finales de qualifs fraichement arrivees reclassees (F -> Q-F)")
    except Exception as exc:  # noqa: BLE001 - ne doit pas faire echouer tout le sync
        print(f"  (reclassification qualifs echouee: {exc})")

    print(f"Termine: {total} matchs synchronises (crees ou mis a jour), {calls} appels API")


if __name__ == "__main__":
    main()
