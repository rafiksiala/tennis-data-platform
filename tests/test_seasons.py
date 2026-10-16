"""Saison d'une edition (ingest/seasons.py + mapping.fixture_season)."""

from datetime import date, datetime, timezone

import pytest

from tennis_data.ingest.mapping import fixture_season
from tennis_data.ingest.seasons import season_for_date


@pytest.mark.parametrize(
    ("day", "season"),
    [
        (date(2026, 1, 1), 2026),
        (date(2026, 9, 5), 2026),
        (date(2025, 12, 25), 2025),
        (date(2025, 12, 26), 2026),  # debut de saison: United Cup, Brisbane...
        (date(2025, 12, 31), 2026),
    ],
)
def test_season_for_date(day, season):
    assert season_for_date(day) == season


class TestFixtureSeason:
    def test_event_date_wins_over_provider_season(self):
        # cas reel: US Open 2026 (R128 -> QF) livre avec tournament_season = 2025
        assert fixture_season({"event_date": "2026-09-05", "tournament_season": "2025"}) == 2026

    def test_event_week_crossing_new_year(self):
        assert fixture_season({"event_date": "2025-12-29", "tournament_season": "2026"}) == 2026
        assert fixture_season({"event_date": "2026-01-03", "tournament_season": "2026"}) == 2026

    def test_falls_back_to_provider_season_without_date(self):
        assert fixture_season({"event_date": None, "tournament_season": "2024"}) == 2024
        assert fixture_season({"event_date": "not a date", "tournament_season": 2023}) == 2023

    def test_falls_back_to_current_year(self):
        assert fixture_season({}) == datetime.now(timezone.utc).year
        assert fixture_season({"tournament_season": "n/a"}) == datetime.now(timezone.utc).year
