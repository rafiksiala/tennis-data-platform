"""Scripts de reparation (tennis_data/repairs), contre Postgres. Rien n'est committe."""

from datetime import datetime, timezone

import pytest
from factories import make_edition, make_match, make_tournament
from sqlalchemy import text

from tennis_data.models import Match, Tournament, TournamentExternalId
from tennis_data.repairs import editions, finals, scheduled_at_utc
from tennis_data.repairs.markers import RepairRefused, applied_at, record_applied

pytestmark = pytest.mark.db

BEFORE_FREEZE = datetime(2026, 9, 9, 6, 0, tzinfo=timezone.utc)  # derniere synchro avant le gel
AFTER_FREEZE = datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc)


def utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def stored_at(session, match) -> datetime:
    session.expire_all()
    return session.get(Match, match.id).scheduled_at


def tournament_of(session, match) -> int:
    session.expire_all()
    return session.get(Match, match.id).tournament_id


class TestScheduledAtUtc:
    def test_shifts_berlin_wall_clock_to_utc(self, db_session):
        t = make_tournament(db_session)
        # valeurs telles que stockees par l'ancien code: heure de Berlin etiquetee UTC
        summer = make_match(db_session, t, utc(2026, 7, 12, 17, 10), last_synced_at=BEFORE_FREEZE)
        winter = make_match(db_session, t, utc(2026, 1, 25, 10, 0), last_synced_at=BEFORE_FREEZE)
        fall_back = make_match(db_session, t, utc(2025, 10, 26, 2, 30), last_synced_at=BEFORE_FREEZE)
        never_synced = make_match(db_session, t, utc(2026, 7, 1, 12, 0), last_synced_at=None)

        preview = scheduled_at_utc.preview(db_session, sample_ids=[summer.id])
        assert (preview.to_shift, preview.shift_2h, preview.shift_1h, preview.synced_after_cutoff) == (4, 2, 2, 0)
        assert preview.samples[0]["repaired"] == utc(2026, 7, 12, 15, 10)

        assert scheduled_at_utc.apply(db_session) == 4

        assert stored_at(db_session, summer) == utc(2026, 7, 12, 15, 10)  # finale de Wimbledon 2026
        assert stored_at(db_session, winter) == utc(2026, 1, 25, 9, 0)
        assert stored_at(db_session, fall_back) == utc(2025, 10, 26, 1, 30)  # heure ambigue -> heure d'hiver
        assert stored_at(db_session, never_synced) == utc(2026, 7, 1, 10, 0)
        assert applied_at(db_session, scheduled_at_utc.NAME) is not None

    def test_never_shifts_twice(self, db_session):
        match = make_match(db_session, make_tournament(db_session), utc(2026, 7, 12, 17, 10), last_synced_at=None)
        scheduled_at_utc.apply(db_session)

        with pytest.raises(RepairRefused, match="deja appliquee"):
            scheduled_at_utc.apply(db_session)
        assert stored_at(db_session, match) == utc(2026, 7, 12, 15, 10)

    def test_refuses_when_ingestion_resumed_after_the_freeze(self, db_session):
        t = make_tournament(db_session)
        old = make_match(db_session, t, utc(2026, 7, 12, 17, 10), last_synced_at=BEFORE_FREEZE)
        make_match(db_session, t, utc(2026, 10, 2, 15, 0), last_synced_at=AFTER_FREEZE)

        with pytest.raises(RepairRefused, match="apres le 2026-09-10"):
            scheduled_at_utc.apply(db_session)
        assert stored_at(db_session, old) == utc(2026, 7, 12, 17, 10)
        assert applied_at(db_session, scheduled_at_utc.NAME) is None

    def test_explicit_cutoff_leaves_rows_written_by_the_fixed_code(self, db_session):
        t = make_tournament(db_session)
        old = make_match(db_session, t, utc(2026, 7, 12, 17, 10), last_synced_at=BEFORE_FREEZE)
        new = make_match(db_session, t, utc(2026, 10, 2, 15, 0), last_synced_at=AFTER_FREEZE)

        assert scheduled_at_utc.apply(db_session, cutoff=utc(2026, 9, 30), cutoff_is_explicit=True) == 1

        assert stored_at(db_session, old) == utc(2026, 7, 12, 15, 10)
        assert stored_at(db_session, new) == utc(2026, 10, 2, 15, 0)


class TestEditions:
    @pytest.fixture(autouse=True)
    def utc_repair_done(self, db_session):
        record_applied(db_session, scheduled_at_utc.NAME, 0)

    def test_us_open_2026_matches_move_to_the_2026_edition(self, db_session):
        # cas reel: tournoi 423 (2025) contient 87 matchs de septembre 2026, le 2203 (2026) les qualifs
        e2025 = make_edition(db_session, "1217", 2025, name="US Open")
        e2026 = make_edition(db_session, "1217", 2026, name="US Open")
        final_2025 = make_match(db_session, e2025, utc(2025, 9, 7, 20, 0), round_code="F")
        qualifying_2026 = make_match(db_session, e2026, utc(2026, 8, 20, 15, 0))
        main_draw_2026 = [make_match(db_session, e2025, utc(2026, 9, d, 16, 0)) for d in (1, 3, 8)]

        plan = editions.plan(db_session)
        assert [(f.action, f.source_id, f.target_id, len(f.match_ids)) for f in plan.fixes] == [
            (editions.MOVE, e2025.id, e2026.id, 3)
        ]
        assert plan.fixes[0].empties_source is False

        editions.apply(db_session)

        assert {tournament_of(db_session, m) for m in main_draw_2026 + [qualifying_2026]} == {e2026.id}
        assert tournament_of(db_session, final_2025) == e2025.id
        assert editions.plan(db_session).fixes == []  # idempotent
        assert applied_at(db_session, editions.NAME) is not None

    def test_whole_edition_with_the_wrong_season_is_relabeled(self, db_session):
        edition = make_edition(db_session, "777", 2025)
        matches = [make_match(db_session, edition, utc(2026, 9, d, 12, 0)) for d in (1, 2)]

        editions.apply(db_session)

        db_session.expire_all()
        assert db_session.get(Tournament, edition.id).season == 2026
        assert [e.external_id for e in db_session.query(TournamentExternalId).filter_by(tournament_id=edition.id)] == [
            "777_2026"
        ]
        assert {tournament_of(db_session, m) for m in matches} == {edition.id}

    def test_missing_edition_is_created(self, db_session):
        edition = make_edition(db_session, "888", 2025, name="Mallorca", tour="atp", surface="Grass")
        stays = make_match(db_session, edition, utc(2025, 6, 25, 12, 0))
        moves = make_match(db_session, edition, utc(2026, 6, 24, 12, 0))

        plan = editions.apply(db_session)

        assert [f.action for f in plan.fixes] == [editions.CREATE]
        created = db_session.query(TournamentExternalId).filter_by(external_id="888_2026").one().tournament
        assert (created.name, created.tour, created.surface, created.season) == ("Mallorca", "atp", "Grass", 2026)
        assert created.external_series_key == "888"
        assert tournament_of(db_session, moves) == created.id
        assert tournament_of(db_session, stays) == edition.id

    def test_late_december_counts_for_next_season(self, db_session):
        edition = make_edition(db_session, "999", 2025, name="Brisbane")
        make_match(db_session, edition, utc(2025, 12, 29, 1, 0))

        assert [(f.action, f.target_season) for f in editions.plan(db_session).fixes] == [(editions.RELABEL, 2026)]

    def test_crossed_editions_are_swapped_without_key_conflict(self, db_session):
        a = make_edition(db_session, "666", 2025)
        b = make_edition(db_session, "666", 2026)
        in_a = make_match(db_session, a, utc(2026, 5, 1, 12, 0))
        in_b = make_match(db_session, b, utc(2025, 5, 1, 12, 0))

        editions.apply(db_session)

        assert (tournament_of(db_session, in_a), tournament_of(db_session, in_b)) == (b.id, a.id)
        assert editions.plan(db_session).fixes == []

    def test_two_sources_share_one_created_edition(self, db_session):
        a = make_edition(db_session, "555", 2024)
        b = make_edition(db_session, "555", 2025)
        make_match(db_session, a, utc(2024, 5, 1, 12, 0))
        make_match(db_session, b, utc(2025, 5, 1, 12, 0))
        from_a = make_match(db_session, a, utc(2026, 5, 1, 12, 0))
        from_b = make_match(db_session, b, utc(2026, 5, 2, 12, 0))

        plan = editions.apply(db_session)

        assert sorted(f.action for f in plan.fixes) == [editions.CREATE, editions.MOVE]
        created = db_session.query(TournamentExternalId).filter_by(external_id="555_2026").one().tournament_id
        assert tournament_of(db_session, from_a) == tournament_of(db_session, from_b) == created

    def test_reports_emptied_sources_without_deleting_them(self, db_session):
        e2025 = make_edition(db_session, "444", 2025)
        make_edition(db_session, "444", 2026)
        make_match(db_session, e2025, utc(2026, 3, 1, 12, 0))

        plan = editions.apply(db_session)

        assert plan.fixes[0].empties_source is True
        assert db_session.get(Tournament, e2025.id) is not None


class TestEditionsDayBoundary:
    def test_day_is_read_as_wall_clock_before_the_utc_repair(self, db_session):
        # stocke 25/12 23:30 "Z" = 23:30 a Berlin le 25/12 (ancien code): saison 2025, rien a faire
        edition = make_edition(db_session, "333", 2025)
        make_match(db_session, edition, utc(2025, 12, 25, 23, 30))

        assert editions.plan(db_session).local_tz == "UTC"
        assert editions.plan(db_session).fixes == []

    def test_day_is_read_in_berlin_after_the_utc_repair(self, db_session):
        # vrai UTC 25/12 23:30Z = 26/12 00:30 a Berlin: saison suivante
        record_applied(db_session, scheduled_at_utc.NAME, 0)
        edition = make_edition(db_session, "333", 2025)
        make_match(db_session, edition, utc(2025, 12, 25, 23, 30))

        plan = editions.plan(db_session)
        assert plan.local_tz == "Europe/Berlin"
        assert [f.target_season for f in plan.fixes] == [2026]

    def test_apply_requires_the_utc_repair(self, db_session):
        with pytest.raises(RepairRefused, match="scheduled-at-utc"):
            editions.apply(db_session)


class TestFinals:
    def test_requires_the_editions_repair(self, db_session):
        with pytest.raises(RepairRefused, match="editions"):
            finals.apply(db_session)

    def test_preview_and_apply(self, db_session):
        edition = make_edition(db_session, "1217", 2026, name="US Open")
        qual_final = make_match(db_session, edition, utc(2026, 8, 21, 12, 0), round_code="F")
        make_match(db_session, edition, utc(2026, 9, 8, 18, 0), round_code="QF")

        assert finals.preview(db_session) == [
            {
                "tournament_id": edition.id,
                "name": "US Open",
                "tour": "atp",
                "season": 2026,
                "demoted": 1,
                "promoted": 0,
            }
        ]

        record_applied(db_session, editions.NAME, 0)
        result = finals.apply(db_session)

        assert (result.demoted, result.promoted) == (1, 0)
        db_session.expire_all()
        assert db_session.get(Match, qual_final.id).round_code == "Q-F"
        assert finals.preview(db_session) == []


def test_previews_run_in_a_read_only_transaction(db_session):
    """La simulation de scripts/repair_data.py tourne en SET TRANSACTION READ ONLY:
    aucune des previews ne doit tenter d'ecrire."""
    edition = make_edition(db_session, "1217", 2025)
    make_match(db_session, edition, utc(2026, 9, 1, 16, 0), round_code="F", last_synced_at=BEFORE_FREEZE)
    make_match(db_session, edition, utc(2026, 9, 2, 16, 0), round_code="F", last_synced_at=BEFORE_FREEZE)

    db_session.execute(text("SET TRANSACTION READ ONLY"))

    assert scheduled_at_utc.preview(db_session).to_shift == 2
    assert len(editions.plan(db_session).fixes) == 1
    assert len(finals.preview(db_session)) == 1
