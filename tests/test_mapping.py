"""Tests du vocabulaire API-Tennis (ingest/mapping.py).

Les libelles bruts viennent de donnees reelles (round_raw en base, 2026-10-16):
"<tournoi> - 1/8-finals", "Quarter-finals", "Semi-finals", "Final".
"""

import pytest

from tennis_data.ingest.mapping import (
    flatten_odds,
    normalize_round,
    normalize_stat_name,
    normalize_status,
    parse_score_component,
    parse_stat_value,
)


class TestNormalizeRound:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("ATP US Open - 1/64-finals", "R128"),
            ("ATP US Open - 1/32-finals", "R64"),
            ("ATP US Open - 1/16-finals", "R32"),
            ("Barranquilla - 1/8-finals", "R16"),
            ("ATP US Open - Quarter-finals", "QF"),
            ("Como - Semi-finals", "SF"),
            ("Mallorca - Final", "F"),
            ("ATP Finals - Round Robin", "RR"),
        ],
    )
    def test_main_draw_rounds(self, raw, expected):
        assert normalize_round(raw) == (expected, raw)

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # Piege reel (2026-08-12): ces trois libelles contiennent "final"
            ("ATP Wimbledon - 1/8-finals", "R16"),
            ("ATP Wimbledon - Quarter-finals", "QF"),
            ("ATP Wimbledon - Semi-finals", "SF"),
        ],
    )
    def test_final_keyword_is_checked_last(self, raw, expected):
        code, _ = normalize_round(raw)
        assert code == expected
        assert code != "F"

    def test_matching_is_case_insensitive(self):
        assert normalize_round("SOMEWHERE - FINAL") == ("F", "SOMEWHERE - FINAL")

    def test_qualification_prefixes_code(self):
        assert normalize_round("Barranquilla - Final", is_qualification=True) == ("Q-F", "Barranquilla - Final")
        assert normalize_round("X - 1/8-finals", is_qualification=True) == ("Q-R16", "X - 1/8-finals")

    @pytest.mark.parametrize("raw", [None, ""])
    def test_missing_round(self, raw):
        assert normalize_round(raw) == (None, raw)

    def test_unknown_round_gives_none_but_keeps_raw(self):
        # mieux vaut NULL qu'une valeur fausse
        assert normalize_round("Davis Cup - Play Offs") == (None, "Davis Cup - Play Offs")


class TestNormalizeStatus:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Finished", "finished"),
            ("Retired", "retired"),
            ("Walk Over", "walkover"),
            ("walkover", "walkover"),
            ("W.O.", "walkover"),
            ("Cancelled", "cancelled"),
            ("Canceled", "cancelled"),
            ("Abandoned", "cancelled"),
            ("Postponed", "postponed"),
            ("  Finished  ", "finished"),
        ],
    )
    def test_known_statuses(self, raw, expected):
        assert normalize_status(raw) == (expected, raw)

    @pytest.mark.parametrize("raw", ["Set 1", "Set 3"])
    def test_set_in_progress_is_live(self, raw):
        assert normalize_status(raw) == ("live", raw)

    def test_not_started_is_scheduled(self):
        assert normalize_status("") == ("scheduled", "")
        assert normalize_status("Not Started") == ("scheduled", "Not Started")

    def test_none_is_scheduled_and_raw_becomes_empty_string(self):
        assert normalize_status(None) == ("scheduled", "")

    def test_unknown_status_is_assumed_live(self):
        assert normalize_status("Interrupted") == ("live", "Interrupted")


class TestParseScoreComponent:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("6", (6, None)),
            ("0", (0, None)),
            (6, (6, None)),
            ("6.4", (6, 4)),
            ("7.10", (7, 10)),
            (None, (None, None)),
            ("", (None, None)),
            ("abc", (None, None)),
            ("6.x", (None, None)),
        ],
    )
    def test_parse(self, raw, expected):
        assert parse_score_component(raw) == expected


class TestParseStatValue:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("62%", 62.0), (" 7 ", 7.0), ("0.5", 0.5), (3, 3.0), (None, None), ("", None), ("n/a", None)],
    )
    def test_parse(self, raw, expected):
        assert parse_stat_value(raw) == expected


class TestNormalizeStatName:
    def test_known_name_is_mapped(self):
        assert normalize_stat_name("1st serve percentage") == "first_serve_pct"

    def test_unknown_name_is_slugified(self):
        assert normalize_stat_name(" Total Points Won % ") == "total_points_won_pct"


class TestFlattenOdds:
    def test_flattens_nested_markets(self):
        odds = {
            "Home/Away": {
                "Home": {"bet365": "1.50", "Pinnacle": "1.52"},
                "Away": {"bet365": "2.60"},
            },
            "Set Betting": {"2:0": {"bet365": "2.10"}},
        }
        assert flatten_odds(odds) == [
            {"market": "Home/Away", "selection": "Home", "bookmaker": "bet365", "value": 1.5},
            {"market": "Home/Away", "selection": "Home", "bookmaker": "Pinnacle", "value": 1.52},
            {"market": "Home/Away", "selection": "Away", "bookmaker": "bet365", "value": 2.6},
            {"market": "Set Betting", "selection": "2:0", "bookmaker": "bet365", "value": 2.1},
        ]

    def test_skips_malformed_levels_and_unparseable_values(self):
        odds = {
            "Broken market": "not a dict",
            "Home/Away": {"Home": ["not", "a", "dict"], "Away": {"bet365": "-", "1xBet": "3.1"}},
        }
        assert flatten_odds(odds) == [
            {"market": "Home/Away", "selection": "Away", "bookmaker": "1xBet", "value": 3.1},
        ]

    @pytest.mark.parametrize("odds", [None, {}])
    def test_empty(self, odds):
        assert flatten_odds(odds) == []
