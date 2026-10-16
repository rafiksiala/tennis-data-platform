"""Tests des indicateurs de forme (analytics/form.py).

summarize_form est teste sans base; compute_player_form et l'endpoint /players/{id}/form
le sont contre Postgres (marque `db`).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
from factories import make_match, make_player, make_tournament

from tennis_data.analytics.form import compute_player_form, summarize_form

PLAYER = 1
OPPONENT = 2
AS_OF = datetime(2026, 7, 1, tzinfo=timezone.utc)


@dataclass
class Row:
    scheduled_at: datetime
    winner_id: int | None
    surface: str | None = "Hard"


def played(days_ago: float, won: bool, surface: str | None = "Hard") -> Row:
    return Row(AS_OF - timedelta(days=days_ago), PLAYER if won else OPPONENT, surface)


class TestSummarizeForm:
    def test_no_matches(self):
        form = summarize_form(PLAYER, AS_OF, [])
        assert form.matches_considered == 0
        assert form.last_n == {10: (0, 0), 20: (0, 0), 30: (0, 0)}
        assert form.win_rate_last_n(10) is None
        assert form.window_months == {3: (0, 0), 6: (0, 0), 12: (0, 0)}
        assert form.win_rate_window(3) is None
        assert form.by_surface == {}
        assert (form.streak_type, form.streak_count) == (None, 0)
        assert form.days_since_last_match is None
        assert form.matches_last_30_days == 0

    def test_last_n_takes_most_recent_first(self):
        # 10 victoires recentes puis 15 defaites plus anciennes
        rows = [played(i + 1, won=True) for i in range(10)] + [played(20 + i, won=False) for i in range(15)]
        form = summarize_form(PLAYER, AS_OF, rows)
        assert form.last_n[10] == (10, 10)
        assert form.last_n[20] == (10, 20)
        assert form.last_n[30] == (10, 25)
        assert form.win_rate_last_n(20) == 0.5

    def test_time_windows_use_30_day_months(self):
        rows = [played(10, won=True), played(89, won=False), played(91, won=True), played(200, won=True)]
        form = summarize_form(PLAYER, AS_OF, rows)
        assert form.window_months[3] == (1, 2)  # cutoff = as_of - 90 jours
        assert form.window_months[6] == (2, 3)
        assert form.window_months[12] == (3, 4)

    def test_by_surface_skips_unknown_surface(self):
        rows = [played(1, True, "Clay"), played(2, False, "Clay"), played(3, True, "Grass"), played(4, True, None)]
        form = summarize_form(PLAYER, AS_OF, rows)
        assert {s: (f.wins, f.matches) for s, f in form.by_surface.items()} == {"Clay": (1, 2), "Grass": (1, 1)}
        assert form.by_surface["Clay"].win_rate == 0.5

    def test_streak_counts_consecutive_results_from_most_recent(self):
        rows = [played(1, False), played(3, False), played(5, True), played(7, False)]
        form = summarize_form(PLAYER, AS_OF, rows)
        assert (form.streak_type, form.streak_count) == ("L", 2)

    def test_naive_as_of_is_read_as_utc(self):
        # review 3.6: un as_of sans fuseau faisait planter la soustraction avec des heures aware
        form = summarize_form(PLAYER, AS_OF.replace(tzinfo=None), [played(2, True), played(40, False)])
        assert form.as_of == AS_OF
        assert form.as_of.tzinfo is timezone.utc
        assert form.days_since_last_match == 2
        assert form.window_months[3] == (1, 2)

    def test_rest_and_workload(self):
        rows = [played(4.5, True), played(29, True), played(31, False)]
        form = summarize_form(PLAYER, AS_OF, rows)
        assert form.days_since_last_match == 4
        assert form.matches_last_30_days == 2


@pytest.mark.db
class TestComputePlayerForm:
    def test_only_finished_matches_before_as_of_are_counted(self, db_session):
        player, opponent = make_player(db_session, "Player"), make_player(db_session, "Opponent")
        clay = make_tournament(db_session, surface="Clay")

        def match(days_ago, winner, status="finished"):
            make_match(
                db_session, clay, AS_OF - timedelta(days=days_ago), player, opponent, winner=winner, status=status
            )

        match(2, player)
        match(5, opponent)
        match(8, player)
        match(3, opponent, status="retired")  # forme = matchs termines uniquement
        match(-1, player)  # apres as_of: ignore (pas de fuite du futur)

        form = compute_player_form(db_session, player.id, AS_OF)

        assert form.matches_considered == 3
        assert form.last_n[10] == (2, 3)
        assert (form.streak_type, form.streak_count) == ("W", 1)
        assert form.by_surface["Clay"].matches == 3
        assert form.days_since_last_match == 2

    def test_form_endpoint(self, db_session, api_client):
        player, opponent = make_player(db_session, "Player"), make_player(db_session, "Opponent")
        make_match(db_session, make_tournament(db_session), AS_OF - timedelta(days=1), player, opponent, winner=player)

        response = api_client.get(f"/players/{player.id}/form", params={"as_of": "2026-07-01T00:00:00Z"})

        assert response.status_code == 200
        body = response.json()
        assert body["matches_considered"] == 1
        assert body["win_rate_last_10"] == 1.0
        assert body["streak_type"] == "W"

    @pytest.mark.parametrize("as_of", ["2026-07-01T00:00:00", "2026-07-01T02:00:00+02:00"])
    def test_form_endpoint_accepts_naive_or_offset_as_of(self, db_session, api_client, as_of):
        player, opponent = make_player(db_session, "Player"), make_player(db_session, "Opponent")
        make_match(db_session, make_tournament(db_session), AS_OF - timedelta(days=1), player, opponent, winner=player)

        response = api_client.get(f"/players/{player.id}/form", params={"as_of": as_of})

        assert response.status_code == 200  # 500 avant le correctif pour la version naive
        assert response.json()["as_of"] == "2026-07-01T00:00:00Z"
        assert response.json()["matches_considered"] == 1
