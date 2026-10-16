"""Endpoints de lecture, contre Postgres."""

from datetime import datetime, timezone

import pytest
from factories import make_match, make_player, make_tournament
from sqlalchemy import text

pytestmark = pytest.mark.db


def test_date_filter_uses_utc_days(db_session, api_client):
    tournament = make_tournament(db_session)
    p1, p2 = make_player(db_session, "A"), make_player(db_session, "B")
    late = make_match(db_session, tournament, datetime(2026, 7, 1, 23, 30, tzinfo=timezone.utc), p1, p2)
    early = make_match(db_session, tournament, datetime(2026, 7, 2, 0, 15, tzinfo=timezone.utc), p1, p2)

    def ids(**params):
        return [m["id"] for m in api_client.get("/matches", params=params).json()["results"]]

    assert ids(date="2026-07-01") == [late.id]
    assert ids(date="2026-07-02") == [early.id]
    assert ids(date_from="2026-07-01", date_to="2026-07-01") == [late.id]
    assert ids(date_from="2026-07-02") == [early.id]


def test_scheduled_at_is_serialized_in_utc(db_session, api_client):
    tournament = make_tournament(db_session)
    match = make_match(db_session, tournament, datetime(2026, 7, 12, 15, 10, tzinfo=timezone.utc))

    body = api_client.get(f"/matches/{match.id}").json()

    assert body["scheduled_at"] == "2026-07-12T15:10:00Z"


def test_database_session_runs_in_utc(db_session):
    assert db_session.execute(text("SHOW timezone")).scalar_one() == "UTC"
