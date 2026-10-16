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


def test_from_to_bounds_select_a_local_day(db_session, api_client):
    """Le jour du 1er juillet a New York (UTC-4) = [2026-07-01T04:00Z, 2026-07-02T04:00Z[,
    ce que le frontend envoie dans from/to (resultats tries du plus recent au plus ancien)."""
    tournament = make_tournament(db_session)
    p1, p2 = make_player(db_session, "A"), make_player(db_session, "B")

    def at(day, hour, minute=0):
        return make_match(db_session, tournament, datetime(2026, 7, day, hour, minute, tzinfo=timezone.utc), p1, p2)

    before = at(1, 3, 59)  # 30 juin 23:59 a New York
    first = at(1, 4)  # minuit pile a New York: inclus
    late = at(2, 2, 30)  # 1er juillet 22:30 a New York, deja le 2 en UTC
    after = at(2, 4)  # minuit le 2 juillet a New York: exclu

    def ids(params):
        response = api_client.get("/matches", params=params)
        assert response.status_code == 200, response.text
        return [m["id"] for m in response.json()["results"]]

    new_york_day = [late.id, first.id]
    assert ids({"from": "2026-07-01T04:00:00Z", "to": "2026-07-02T04:00:00Z"}) == new_york_day
    # format exact de Date.toISOString() cote navigateur
    assert ids({"from": "2026-07-01T04:00:00.000Z", "to": "2026-07-02T04:00:00.000Z"}) == new_york_day
    assert ids({"from": "2026-07-01T00:00:00-04:00", "to": "2026-07-02T00:00:00-04:00"}) == new_york_day
    # sans fuseau = UTC
    assert ids({"from": "2026-07-01T04:00:00", "to": "2026-07-02T04:00:00"}) == new_york_day
    # le meme jour a Paris (UTC+2): 30 juin 22:00Z -> 1er juillet 22:00Z
    assert ids({"from": "2026-07-01T00:00:00+02:00", "to": "2026-07-02T00:00:00+02:00"}) == [first.id, before.id]

    assert ids({"from": "2026-07-02T02:30:00Z"}) == [after.id, late.id]
    assert ids({"to": "2026-07-01T04:00:00Z"}) == [before.id]
    # le jour UTC reste disponible pour les autres clients, et se combine avec from/to
    assert ids({"date": "2026-07-01"}) == [first.id, before.id]
    assert ids({"date": "2026-07-01", "from": "2026-07-01T04:00:00Z"}) == [first.id]


@pytest.mark.parametrize(
    "params",
    [
        {"from": "2026-07-02T00:00:00Z", "to": "2026-07-01T00:00:00Z"},
        {"from": "2026-07-01T00:00:00Z", "to": "2026-07-01T00:00:00Z"},
        # naif (UTC 02:00) contre instant avec fuseau (UTC 01:00): compares apres conversion
        {"from": "2026-07-01T02:00:00", "to": "2026-07-01T00:00:00-01:00"},
        {"from": "pas-une-date"},
    ],
)
def test_from_to_rejects_empty_or_invalid_intervals(db_session, api_client, params):
    assert api_client.get("/matches", params=params).status_code == 422


def test_scheduled_at_is_serialized_in_utc(db_session, api_client):
    tournament = make_tournament(db_session)
    match = make_match(db_session, tournament, datetime(2026, 7, 12, 15, 10, tzinfo=timezone.utc))

    body = api_client.get(f"/matches/{match.id}").json()

    assert body["scheduled_at"] == "2026-07-12T15:10:00Z"


def test_database_session_runs_in_utc(db_session):
    assert db_session.execute(text("SHOW timezone")).scalar_one() == "UTC"
