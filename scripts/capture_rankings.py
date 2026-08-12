"""
Capture hebdomadaire des classements ATP/WTA.

A LANCER MAINTENANT (une premiere fois manuellement) puis chaque semaine (ex: tous les
lundis) via le planificateur de taches. C'est la SEULE facon de construire un historique
de classement precis a la semaine - l'API ne fournit que le classement courant, donc
chaque semaine sans cette capture est une semaine d'historique perdue definitivement.

Usage:
    python scripts/capture_rankings.py
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tennis_data.db import get_session
from tennis_data.ingest.upsert import get_or_create_player
from tennis_data.models import IngestRun, RankingSnapshot
from tennis_data.providers.api_tennis import ApiTennisClient

TOURS = ["ATP", "WTA"]


def main():
    client = ApiTennisClient()
    today = datetime.now(timezone.utc).date()

    with get_session() as session:
        run = IngestRun(job_name="capture_rankings")
        session.add(run)
        session.flush()

        inserted = 0
        for tour in TOURS:
            standings = client.get_standings(tour)
            print(f"{tour}: {len(standings)} joueurs classes")
            for row in standings:
                player = get_or_create_player(session, row.get("player_key"), row.get("player"))
                existing = (
                    session.query(RankingSnapshot)
                    .filter_by(
                        player_id=player.id,
                        tour=tour.lower(),
                        snapshot_date=today,
                        source="api_tennis_standings_live",
                    )
                    .one_or_none()
                )
                if existing:
                    existing.rank = _to_int(row.get("place"))
                    existing.points = _to_int(row.get("points"))
                    continue
                session.add(
                    RankingSnapshot(
                        player_id=player.id,
                        tour=tour.lower(),
                        snapshot_date=today,
                        rank=_to_int(row.get("place")),
                        points=_to_int(row.get("points")),
                        source="api_tennis_standings_live",
                        precision="weekly",
                    )
                )
                inserted += 1

        run.status = "success"
        run.finished_at = datetime.now(timezone.utc)
        run.rows_inserted = inserted
        run.api_calls_made = len(TOURS)
        print(f"Termine: {inserted} nouveaux snapshots de classement pour le {today}")


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    main()
