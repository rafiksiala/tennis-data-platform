"""Test de bout en bout sur un tout petit echantillon reel avant de lancer le vrai backfill."""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sqlalchemy import text

from tennis_data.db import get_session
from tennis_data.ingest.upsert import upsert_match_from_fixture
from tennis_data.providers.api_tennis import EVENT_TYPES, ApiTennisClient


def main():
    client = ApiTennisClient()
    date_stop = datetime.now().date()
    date_start = date_stop - timedelta(days=3)
    fixtures = client.get_fixtures_range(str(date_start), str(date_stop), event_type_key=EVENT_TYPES["atp_singles"])
    print(f"{len(fixtures)} fixtures ATP Singles recuperees ({date_start} -> {date_stop})")

    with get_session() as session:
        for fx in fixtures:
            upsert_match_from_fixture(session, fx)
        session.flush()

        n_players = session.execute(text("select count(*) from players")).scalar()
        n_tournaments = session.execute(text("select count(*) from tournaments")).scalar()
        n_matches = session.execute(text("select count(*) from matches")).scalar()
        n_sets = session.execute(text("select count(*) from match_sets")).scalar()
        n_stats = session.execute(text("select count(*) from match_statistics")).scalar()
        print(f"players={n_players} tournaments={n_tournaments} matches={n_matches} sets={n_sets} stats={n_stats}")

    print("Relance du meme script pour verifier l'idempotence (aucun doublon attendu)...")
    with get_session() as session:
        for fx in fixtures:
            upsert_match_from_fixture(session, fx)
        session.flush()
        n_matches_2 = session.execute(text("select count(*) from matches")).scalar()
        print(f"matches apres 2e run = {n_matches_2} (doit etre identique)")


if __name__ == "__main__":
    main()
