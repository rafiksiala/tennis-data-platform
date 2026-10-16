"""Ingestion d'une fixture API-Tennis (upsert.py quotidien et bulk_upsert.py backfill), contre Postgres."""

from datetime import datetime, timedelta, timezone

import pytest

from tennis_data.ingest.bulk_upsert import BulkCache, bulk_upsert_fixtures
from tennis_data.ingest.upsert import upsert_match_from_fixture
from tennis_data.models import Match

pytestmark = pytest.mark.db


def fixture(**overrides) -> dict:
    """Forme reelle d'un element de get_fixtures()['result'] (champs utilises par l'ingestion)."""
    fx = {
        "event_key": 9001,
        "event_date": "2026-09-05",
        "event_time": "18:00",
        "event_first_player": "J. Sinner",
        "first_player_key": 101,
        "event_second_player": "C. Alcaraz",
        "second_player_key": 102,
        "event_final_result": "2 - 0",
        "event_winner": "First Player",
        "event_status": "Finished",
        "event_type_type": "Atp Singles",
        "tournament_name": "US Open",
        "tournament_key": 1217,
        "tournament_round": "ATP US Open - Quarter-finals",
        "tournament_season": "2026",
        "event_qualification": "False",
        "scores": [
            {"score_first": "6", "score_second": "4", "score_set": "1"},
            {"score_first": "7.7", "score_second": "6.5", "score_set": "2"},
        ],
        "statistics": [],
    }
    fx.update(overrides)
    return fx


def reload(session, match_id: int) -> Match:
    session.expire_all()
    return session.get(Match, match_id)


class TestScheduledAtIsUtc:
    def test_daily_upsert_converts_berlin_time(self, db_session):
        match = upsert_match_from_fixture(db_session, fixture())
        db_session.flush()

        stored = reload(db_session, match.id)
        assert stored.scheduled_at == datetime(2026, 9, 5, 16, 0, tzinfo=timezone.utc)  # 18:00 a Berlin (ete)
        assert stored.scheduled_at.utcoffset() == timedelta(0)

    def test_daily_upsert_stamps_last_synced_at_in_utc(self, db_session):
        before = datetime.now(timezone.utc)
        match = upsert_match_from_fixture(db_session, fixture())
        db_session.flush()

        stored = reload(db_session, match.id)
        assert before - timedelta(seconds=5) <= stored.last_synced_at <= datetime.now(timezone.utc)

    def test_backfill_converts_berlin_time(self, db_session):
        cache = BulkCache(db_session)
        assert bulk_upsert_fixtures(db_session, [fixture(event_date="2026-01-20", event_time="10:30")], cache, {}) == 1

        stored = reload(db_session, cache.match_ids["9001"])
        assert stored.scheduled_at == datetime(2026, 1, 20, 9, 30, tzinfo=timezone.utc)  # 10:30 a Berlin (hiver)

    def test_upsert_is_idempotent(self, db_session):
        first = upsert_match_from_fixture(db_session, fixture())
        db_session.flush()
        second = upsert_match_from_fixture(db_session, fixture(event_time="18:30"))
        db_session.flush()

        assert first.id == second.id
        assert db_session.query(Match).count() == 1
        assert reload(db_session, first.id).scheduled_at == datetime(2026, 9, 5, 16, 30, tzinfo=timezone.utc)


class TestEditionSeason:
    def test_provider_season_is_ignored_when_it_contradicts_the_date(self, db_session):
        qualifying = upsert_match_from_fixture(
            db_session, fixture(event_key=1, event_date="2026-08-20", tournament_season="2026")
        )
        main_draw = upsert_match_from_fixture(
            db_session, fixture(event_key=2, event_date="2026-09-01", tournament_season="2025")
        )
        db_session.flush()

        assert qualifying.tournament_id == main_draw.tournament_id
        assert qualifying.tournament.season == 2026

    def test_previous_edition_stays_separate(self, db_session):
        edition_2025 = upsert_match_from_fixture(db_session, fixture(event_key=1, event_date="2025-09-01"))
        edition_2026 = upsert_match_from_fixture(db_session, fixture(event_key=2, event_date="2026-09-01"))
        db_session.flush()

        assert edition_2025.tournament_id != edition_2026.tournament_id
        assert (edition_2025.tournament.season, edition_2026.tournament.season) == (2025, 2026)
        assert edition_2025.tournament.external_series_key == edition_2026.tournament.external_series_key == "1217"

    def test_backfill_uses_the_same_rule(self, db_session):
        cache = BulkCache(db_session)
        fixtures = [
            fixture(event_key=1, event_date="2026-08-20", tournament_season="2026"),
            fixture(event_key=2, event_date="2026-09-01", tournament_season="2025"),
        ]
        assert bulk_upsert_fixtures(db_session, fixtures, cache, {}) == 2

        assert set(cache.tournament_ids) == {"1217_2026"}
        assert {m.tournament_id for m in db_session.query(Match)} == {cache.tournament_ids["1217_2026"]}
