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
from tennis_data.ingest.upsert import upsert_match_from_fixture
from tennis_data.models import IngestRun
from tennis_data.providers.api_tennis import EVENT_TYPES, ApiTennisClient

TOURS = ["atp_singles", "wta_singles", "challenger_men_singles", "challenger_women_singles"]
LOOKBACK_DAYS = 14
LOOKAHEAD_DAYS = 5


def main():
    client = ApiTennisClient()
    surface_lookup = build_surface_lookup(client)

    date_start = str(datetime.now().date() - timedelta(days=LOOKBACK_DAYS))
    date_stop = str(datetime.now().date() + timedelta(days=LOOKAHEAD_DAYS))

    with get_session() as session:
        run = IngestRun(job_name="daily_sync")
        session.add(run)
        session.flush()

        total, calls = 0, 0
        for tour_key in TOURS:
            fixtures = client.get_fixtures_range(date_start, date_stop, event_type_key=EVENT_TYPES[tour_key])
            calls += -(-((datetime.strptime(date_stop, "%Y-%m-%d") - datetime.strptime(date_start, "%Y-%m-%d")).days + 1) // 7)
            print(f"[{tour_key}] {len(fixtures)} matchs sur la fenetre {date_start} -> {date_stop}")
            for fx in fixtures:
                upsert_match_from_fixture(session, fx, tour_surface_lookup=surface_lookup)
            session.flush()
            total += len(fixtures)
            time.sleep(0.3)

        run.status = "success"
        run.finished_at = datetime.now(timezone.utc)
        run.rows_inserted = total
        run.api_calls_made = calls
        print(f"Termine: {total} matchs synchronises (crees ou mis a jour)")


if __name__ == "__main__":
    main()
