# CLAUDE.md

Guidance for Claude Code (and humans) working in this repo. Read `README.md` and
`docs/review-2026-10.md` (verified issues, known data caveats) before larger changes.

## What this is

Intelligence-first sports data platform, tennis first (ATP, WTA, Challenger singles, 2021 → 2026-09-09).
Python 3.12 / FastAPI / SQLAlchemy 2 / Alembic / Postgres 16 on Render; React 19 + Vite frontend in `frontend/`.
Data comes from API-Tennis. Two developers (Rafik and a partner) work in this repo.

## Commands

```bash
uv sync                                  # create .venv with runtime + dev dependencies
uv run pytest                            # tests (DB tests are skipped without TEST_DATABASE_URL)
uv run ruff check . && uv run ruff format --check .
uv run uvicorn tennis_data.api.main:app --reload   # API on :8000, docs at /docs
uv run alembic upgrade head              # apply migrations to DATABASE_URL
cd frontend && npm ci && npx tsc -b && npm run lint && npm test
```

- After changing dependencies in `pyproject.toml`: `uv lock`, then
  `uv export --no-dev --no-hashes --frozen -o requirements.txt` (Render installs from
  `requirements.txt`; CI fails if it drifts from `uv.lock`).
- DB tests (`@pytest.mark.db`) need a **throwaway local** Postgres in `TEST_DATABASE_URL`
  (e.g. `postgresql+psycopg2://tennis:tennis_dev_password@localhost:55432/tennis_test`).
  The fixtures refuse non-local hosts and roll back every test. CI provides one.

## Layout

- `src/tennis_data/models.py`: data model; read its docstring first.
- `src/tennis_data/ingest/mapping.py`: the **only** place that knows API-Tennis vocabulary.
- `src/tennis_data/ingest/upsert.py` (daily, idempotent) and `bulk_upsert.py` (backfill, insert-only).
- `src/tennis_data/analytics/`: derived indicators, always with an `as_of` cut-off (point-in-time).
- `src/tennis_data/api/`: read-only FastAPI app.
- `scripts/`: ingestion jobs and one-off repairs. `migrations/`: Alembic. `tests/`: pytest.

## Conventions

- **Language:** code comments, docstrings, commit messages and `TODO.md` in French;
  shared docs (`README.md`, `docs/`, this file) in English.
- **Decisions:** record significant design decisions as an ADR in `docs/adr/` (numbered, short).
- **Schema changes:** always through a new Alembic migration (`alembic revision --autogenerate -m "..."`),
  reviewed by hand. CI runs `alembic upgrade head` + `alembic check`.
- **Time:** store and compare UTC only (`timestamptz`, aware datetimes); provider times are
  converted at ingestion (ADR-0003). Treat naive inputs as UTC.
- **Point-in-time:** anything describing "before a match" must only use data available at that moment.
- **Tests:** new logic comes with tests; keep pure logic separate from DB access so it can be
  tested without Postgres. Keep `ruff check` and `ruff format` clean.
- Keep PRs small and focused; don't reformat or refactor unrelated code (two people share this repo).

## Safety rules

- **The production database is frozen at 2026-09-09 on purpose.** Do not restart ingestion,
  run backfills or re-enable the Render cron jobs unless Rafik explicitly asks.
- **Never run a script that writes to a database without Rafik's explicit go-ahead** for that
  run, and a fresh backup first. That covers `scripts/backfill_*.py`, `daily_sync.py`,
  `sync_odds.py`, `capture_rankings.py`, `enrich_players.py`, `fix_*.py`, `smoke_test.py`,
  `repair_*.py` with `--apply`, and `alembic upgrade` against anything but a local database.
- Repair scripts must be idempotent and dry-run by default.
- Never point tests or experiments at the production `DATABASE_URL`. Never commit `.env` or keys.
- API-Tennis has a daily quota (8,000 requests on the Starter plan); don't call it in loops or tests.
