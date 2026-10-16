"""Reetiquetages des finales et des QF/SF de qualifs (ingest/maintenance.py), contre Postgres."""

from datetime import datetime, timedelta, timezone

import pytest
from factories import make_match, make_tournament

from tennis_data.ingest.maintenance import (
    preview_finals_relabel,
    preview_qualifying_relabel,
    relabel_finals,
    relabel_qualifying_rounds,
)

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


# --- QF/SF de qualifs -------------------------------------------------------------------


def day(d: int, hour: int = 12, minute: int = 0) -> datetime:
    """Jour d'un US Open fictif: qualifs du 1 au 4 aout, tableau a partir du 6."""
    return datetime(2026, 8, d, hour, minute, tzinfo=timezone.utc)


def test_qualifying_quarters_and_semis_before_the_main_draw_are_relabeled(db_session):
    # qualifs de Grand Chelem Q1/Q2 telles que livrees sans event_qualification: 'QF'/'SF'
    edition = make_tournament(db_session)
    q1 = make_match(db_session, edition, day(1), round_code="QF")
    q2 = make_match(db_session, edition, day(3), round_code="SF")
    make_match(db_session, edition, day(6), round_code="R128")
    make_match(db_session, edition, day(10), round_code="R16")
    real_qf = make_match(db_session, edition, day(12), round_code="QF")
    real_sf = make_match(db_session, edition, day(14), round_code="SF")

    result = relabel_qualifying_rounds(db_session)

    assert codes(db_session, [q1, q2, real_qf, real_sf]) == ["Q-QF", "Q-SF", "QF", "SF"]
    assert (result.demoted, result.promoted) == (2, 0)


def test_qualifying_semi_scheduled_after_the_first_main_draw_match(db_session):
    # Bordeaux 2022: 1er tour de qualifs programme 30 min apres le premier R32, le meme jour
    edition = make_tournament(db_session)
    make_match(db_session, edition, day(6, 13, 15), round_code="R32")
    qualifying = make_match(db_session, edition, day(6, 13, 45), round_code="SF")
    make_match(db_session, edition, day(8), round_code="R16")

    relabel_qualifying_rounds(db_session)

    assert codes(db_session, [qualifying]) == ["Q-SF"]


def test_in_progress_edition_without_r16_uses_the_first_round(db_session):
    # US Open 2026 gele avant le R16 (tournoi 2203): 2 'SF' de qualifs avant le R128
    edition = make_tournament(db_session)
    qualifying = make_match(db_session, edition, day(3), round_code="SF")
    make_match(db_session, edition, day(6), round_code="R128")

    relabel_qualifying_rounds(db_session)

    assert codes(db_session, [qualifying]) == ["Q-SF"]


def test_edition_without_elimination_rounds_is_left_alone(db_session):
    # Masters de fin d'annee: round robin (round_code NULL), puis SF et F
    edition = make_tournament(db_session, name="Finals - Turin")
    make_match(db_session, edition, day(1), round_code=None)
    semis = [make_match(db_session, edition, day(6, hour), round_code="SF") for hour in (14, 19)]

    assert relabel_qualifying_rounds(db_session).total == 0
    assert codes(db_session, semis) == ["SF", "SF"]


def test_heuristic_q_sf_after_the_main_draw_start_becomes_sf_again(db_session):
    edition = make_tournament(db_session)
    make_match(db_session, edition, day(6), round_code="R32")
    make_match(db_session, edition, day(8), round_code="R16")
    real_sf = make_match(db_session, edition, day(12), round_code="Q-SF", is_qualification=False)

    result = relabel_qualifying_rounds(db_session)

    assert codes(db_session, [real_sf]) == ["SF"]
    assert (result.demoted, result.promoted) == (0, 1)


def test_provider_flagged_matches_are_neither_touched_nor_anchors(db_session):
    edition = make_tournament(db_session)
    flagged = make_match(db_session, edition, day(12), round_code="Q-SF", is_qualification=True)
    make_match(db_session, edition, day(1), round_code="R32", is_qualification=True)  # pas un repere
    make_match(db_session, edition, day(6), round_code="R32")
    unflagged = make_match(db_session, edition, day(5), round_code="SF")

    relabel_qualifying_rounds(db_session)

    assert codes(db_session, [flagged, unflagged]) == ["Q-SF", "Q-SF"]


def test_lower_rounds_and_finals_are_not_this_rule(db_session):
    edition = make_tournament(db_session)
    qualifying_final = make_match(db_session, edition, day(4), round_code="F")  # relabel_finals s'en charge
    make_match(db_session, edition, day(6), round_code="R32")
    r16 = make_match(db_session, edition, day(8), round_code="R16")

    assert relabel_qualifying_rounds(db_session).total == 0
    assert codes(db_session, [qualifying_final, r16]) == ["F", "R16"]


def test_qualifying_editions_are_independent(db_session):
    early = make_tournament(db_session, season=2025)
    make_match(db_session, early, day(1) - timedelta(days=365), round_code="R32")
    late = make_tournament(db_session, season=2026)
    qualifying = make_match(db_session, late, day(3), round_code="SF")  # apres le R32 de l'autre edition
    make_match(db_session, late, day(6), round_code="R32")

    relabel_qualifying_rounds(db_session)

    assert codes(db_session, [qualifying]) == ["Q-SF"]


def test_qualifying_preview_lists_changes_without_writing(db_session):
    edition = make_tournament(db_session)
    qualifying = make_match(db_session, edition, day(3), round_code="SF")
    make_match(db_session, edition, day(6), round_code="R32")
    real_sf = make_match(db_session, edition, day(12), round_code="SF")

    preview = preview_qualifying_relabel(db_session)

    assert [(row["id"], row["old_code"], row["new_code"]) for row in preview] == [(qualifying.id, "SF", "Q-SF")]
    assert codes(db_session, [qualifying, real_sf]) == ["SF", "SF"]


def test_qualifying_relabel_is_idempotent(db_session):
    edition = make_tournament(db_session)
    for hour in (10, 12, 14):
        make_match(db_session, edition, day(3, hour), round_code="SF")
    make_match(db_session, edition, day(6), round_code="R32")

    assert relabel_qualifying_rounds(db_session).total == 3
    assert relabel_qualifying_rounds(db_session).total == 0
    assert preview_qualifying_relabel(db_session) == []
