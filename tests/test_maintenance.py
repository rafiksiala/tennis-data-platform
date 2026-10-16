"""Reetiquetage des finales (ingest/maintenance.py), contre Postgres."""

from datetime import datetime, timedelta, timezone

import pytest
from factories import make_match, make_tournament

from tennis_data.ingest.maintenance import preview_finals_relabel, relabel_finals

pytestmark = pytest.mark.db

QUALIFYING_DAY = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)
FINAL_DAY = datetime(2026, 9, 13, 20, 0, tzinfo=timezone.utc)


def codes(session, matches) -> list[str]:
    session.expire_all()
    return [m.round_code for m in matches]


def qualifying_finals(session, tournament, n=3):
    """Finales de qualifs telles que livrees quand event_qualification est absent: 'F'."""
    return [make_match(session, tournament, QUALIFYING_DAY + timedelta(hours=i), round_code="F") for i in range(n)]


def test_in_progress_edition_has_no_real_final(db_session):
    # US Open 2026 gele a l'etat QF (tournoi 2203, review 3.4): l'ancienne regle laissait 'F'
    # sur la finale de qualifs la plus tardive.
    edition = make_tournament(db_session)
    quals = qualifying_finals(db_session, edition)
    make_match(db_session, edition, datetime(2026, 9, 8, 18, 0, tzinfo=timezone.utc), round_code="QF")

    result = relabel_finals(db_session)

    assert codes(db_session, quals) == ["Q-F", "Q-F", "Q-F"]
    assert (result.demoted, result.promoted) == (3, 0)


def test_completed_edition_keeps_its_real_final(db_session):
    edition = make_tournament(db_session)
    quals = qualifying_finals(db_session, edition)
    make_match(db_session, edition, FINAL_DAY - timedelta(days=2), round_code="SF")
    final = make_match(db_session, edition, FINAL_DAY, round_code="F")

    relabel_finals(db_session)

    assert codes(db_session, quals + [final]) == ["Q-F", "Q-F", "Q-F", "F"]


def test_heuristic_q_f_that_is_the_last_match_becomes_f_again(db_session):
    edition = make_tournament(db_session)
    make_match(db_session, edition, FINAL_DAY - timedelta(days=2), round_code="SF")
    final = make_match(db_session, edition, FINAL_DAY, round_code="Q-F", is_qualification=False)

    result = relabel_finals(db_session)

    assert codes(db_session, [final]) == ["F"]
    assert (result.demoted, result.promoted) == (0, 1)


def test_provider_flagged_qualifying_matches_are_never_touched(db_session):
    edition = make_tournament(db_session)
    qual_final = make_match(db_session, edition, FINAL_DAY, round_code="Q-F", is_qualification=True)

    assert relabel_finals(db_session).total == 0
    assert codes(db_session, [qual_final]) == ["Q-F"]


def test_editions_are_independent(db_session):
    finished = make_tournament(db_session, season=2025)
    final_2025 = make_match(db_session, finished, FINAL_DAY - timedelta(days=365), round_code="F")
    in_progress = make_tournament(db_session, season=2026)
    quals = qualifying_finals(db_session, in_progress, n=1)
    make_match(db_session, in_progress, QUALIFYING_DAY + timedelta(days=5), round_code="R128")

    relabel_finals(db_session)

    assert codes(db_session, [final_2025] + quals) == ["F", "Q-F"]


def test_preview_lists_changes_without_writing(db_session):
    edition = make_tournament(db_session)
    quals = qualifying_finals(db_session, edition, n=2)
    final = make_match(db_session, edition, FINAL_DAY, round_code="F")

    preview = preview_finals_relabel(db_session)

    assert {(row["id"], row["old_code"], row["new_code"]) for row in preview} == {
        (quals[0].id, "F", "Q-F"),
        (quals[1].id, "F", "Q-F"),
    }
    assert codes(db_session, quals + [final]) == ["F", "F", "F"]


def test_is_idempotent(db_session):
    edition = make_tournament(db_session)
    qualifying_finals(db_session, edition)
    make_match(db_session, edition, FINAL_DAY, round_code="F")

    assert relabel_finals(db_session).total == 3
    assert relabel_finals(db_session).total == 0
    assert preview_finals_relabel(db_session) == []
