"""Fraicheur des donnees (monitoring.py) et /health."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from factories import make_match, make_tournament
from sqlalchemy.exc import OperationalError

from tennis_data.api import main
from tennis_data.models import IngestRun
from tennis_data.monitoring import FreshnessCache, data_freshness

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
MATCH_DAY = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)


def synced(session, tour: str, hours_ago: float):
    make_match(session, make_tournament(session, tour=tour), MATCH_DAY, last_synced_at=NOW - timedelta(hours=hours_ago))


def run(session, job_name: str, status: str, hours_ago: float):
    session.add(IngestRun(job_name=job_name, status=status, finished_at=NOW - timedelta(hours=hours_ago)))
    session.flush()


@pytest.mark.db
class TestDataFreshness:
    def test_reports_last_sync_per_tour(self, db_session):
        synced(db_session, "atp", hours_ago=30)
        synced(db_session, "atp", hours_ago=2)
        synced(db_session, "wta", hours_ago=40)

        freshness = data_freshness(db_session, NOW)

        assert freshness["tours"] == {
            "atp": {"last_synced_at": "2026-10-16T10:00:00Z", "age_hours": 2.0, "stale": False},
            "wta": {"last_synced_at": "2026-10-14T20:00:00Z", "age_hours": 40.0, "stale": True},
        }
        assert freshness["stale"] is True
        assert freshness["checked_at"] == "2026-10-16T12:00:00Z"

    def test_fresh_when_every_tour_synced_recently(self, db_session):
        synced(db_session, "atp", hours_ago=1)
        synced(db_session, "wta", hours_ago=35)

        assert data_freshness(db_session, NOW)["stale"] is False

    def test_never_synced_tour_is_stale(self, db_session):
        make_match(db_session, make_tournament(db_session, tour="atp"), MATCH_DAY, last_synced_at=None)

        freshness = data_freshness(db_session, NOW)

        assert freshness["tours"]["atp"] == {"last_synced_at": None, "age_hours": None, "stale": True}
        assert freshness["stale"] is True

    def test_empty_database_is_stale(self, db_session):
        assert data_freshness(db_session, NOW)["stale"] is True

    def test_last_successful_run_per_job_family(self, db_session):
        run(db_session, "daily_sync:atp_singles", "success", hours_ago=30)
        run(db_session, "daily_sync:wta_singles", "success", hours_ago=29)
        run(db_session, "daily_sync:atp_singles", "failed", hours_ago=5)
        run(db_session, "sync_odds", "success", hours_ago=28)

        assert data_freshness(db_session, NOW)["last_successful_runs"] == {
            "daily_sync": "2026-10-15T07:00:00Z",
            "sync_odds": "2026-10-15T08:00:00Z",
        }


class TestFreshnessCache:
    def test_reuses_value_within_ttl(self, monkeypatch):
        calls = []
        monkeypatch.setattr("tennis_data.monitoring.data_freshness", lambda session, now: calls.append(now) or {"n": 1})
        cache = FreshnessCache(ttl=timedelta(minutes=5))

        cache.get(Mock(), NOW)
        cache.get(Mock(), NOW + timedelta(minutes=4))
        assert len(calls) == 1

        cache.get(Mock(), NOW + timedelta(minutes=6))
        assert len(calls) == 2

    def test_database_error_is_reported_and_not_cached(self):
        session = Mock()
        session.query.side_effect = OperationalError("SELECT 1", {}, Exception("connection refused"))
        cache = FreshnessCache(ttl=timedelta(minutes=5))

        assert cache.get(session, NOW) == {"error": "database unreachable"}
        assert cache._value is None


@pytest.mark.db
def test_health_endpoint_is_200_even_when_data_is_stale(db_session, api_client):
    main._freshness.clear()
    synced(db_session, "atp", hours_ago=24 * 37)  # base gelee depuis des semaines

    response = api_client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["data"]["stale"] is True
    assert body["data"]["tours"]["atp"]["stale"] is True
    main._freshness.clear()
