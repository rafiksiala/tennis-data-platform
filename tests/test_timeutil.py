"""Conversions vers UTC (timeutil.py) et coherence avec Postgres AT TIME ZONE."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from tennis_data.timeutil import as_utc, wall_time_to_utc

BERLIN = ZoneInfo("Europe/Berlin")


def utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


# (heure murale de Berlin, instant UTC attendu)
BERLIN_CASES = [
    (datetime(2026, 7, 12, 17, 10), utc(2026, 7, 12, 15, 10)),  # ete: UTC+2
    (datetime(2026, 1, 25, 10, 0), utc(2026, 1, 25, 9, 0)),  # hiver: UTC+1
    (datetime(2026, 7, 12, 0, 30), utc(2026, 7, 11, 22, 30)),  # change de jour UTC
    # passage a l'heure d'ete (29/03/2026): 02:30 n'existe pas -> lu comme heure d'hiver
    (datetime(2026, 3, 29, 2, 30), utc(2026, 3, 29, 1, 30)),
    # passage a l'heure d'hiver (25/10/2026): 02:30 existe deux fois -> heure d'hiver
    (datetime(2026, 10, 25, 2, 30), utc(2026, 10, 25, 1, 30)),
    (datetime(2026, 10, 25, 1, 59), utc(2026, 10, 24, 23, 59)),  # juste avant: encore l'ete
    (datetime(2026, 10, 25, 3, 0), utc(2026, 10, 25, 2, 0)),  # juste apres: hiver
]


class TestWallTimeToUtc:
    @pytest.mark.parametrize(("wall", "expected"), BERLIN_CASES)
    def test_berlin(self, wall, expected):
        result = wall_time_to_utc(wall.replace(tzinfo=BERLIN))
        assert result == expected
        assert result.utcoffset() == timedelta(0)

    @pytest.mark.parametrize("fold", [0, 1])
    def test_fold_is_ignored(self, fold):
        ambiguous = datetime(2026, 10, 25, 2, 30, fold=fold, tzinfo=BERLIN)
        assert wall_time_to_utc(ambiguous) == utc(2026, 10, 25, 1, 30)


class TestAsUtc:
    def test_naive_is_taken_as_utc(self):
        assert as_utc(datetime(2026, 7, 1)) == utc(2026, 7, 1)
        assert as_utc(datetime(2026, 7, 1)).tzinfo is timezone.utc

    def test_aware_is_converted(self):
        paris_noon = datetime(2026, 7, 1, 12, 0, tzinfo=ZoneInfo("Europe/Paris"))
        assert as_utc(paris_noon) == utc(2026, 7, 1, 10, 0)
        assert as_utc(paris_noon).tzinfo is timezone.utc


@pytest.mark.db
@pytest.mark.parametrize(("wall", "expected"), BERLIN_CASES)
def test_matches_postgres_at_time_zone(db_session, wall, expected):
    """Le script de reparation decale les lignes existantes en SQL (AT TIME ZONE): il doit
    donner exactement le meme instant que l'ingestion Python, y compris aux changements d'heure."""
    from_postgres = db_session.execute(
        text("SELECT CAST(:wall AS timestamp) AT TIME ZONE 'Europe/Berlin'"), {"wall": wall}
    ).scalar_one()
    assert from_postgres == expected == wall_time_to_utc(wall.replace(tzinfo=BERLIN))
