# Runbook: repairing existing rows (October 2026)

Status: **not run.** Running it needs Rafik's explicit go-ahead and a fresh backup.

The P0 code fixes (PR "Foundations 2/4") only affect rows written from now on. This runbook covers
the rows already in the production database. It uses `scripts/repair_data.py`, which wraps three
repairs from `src/tennis_data/repairs/`:

| # | Repair | Review | What it changes | Idempotent by |
|---|---|---|---|---|
| 1 | `scheduled-at-utc` | 3.5, [ADR-0003](../adr/0003-utc-timestamps.md) | Every `matches.scheduled_at` written by the old code is reread as Europe/Berlin and converted to UTC (−2 h in summer, −1 h in winter) | an `ingest_runs` marker (a second run is refused) + `last_synced_at` cut-off |
| 2 | `editions` | 3.3 | Re-attaches matches to the edition of their real season (e.g. 87 Sept-2026 US Open matches from tournament 423 to 2203); relabels or creates editions where needed | nature (a second run finds nothing to move) |
| 3 | `finals` | 3.4 | Re-labels `F`/`Q-F` everywhere with the rule "the real final is the last match of its edition" | nature |

Every repair is **dry-run by default**. A dry run uses a `READ ONLY` transaction, so it cannot write.
With `--apply`, the script works in one transaction:
1. it asks you to type the database name;
2. it applies the repair and writes its `repair:<name>` marker to `ingest_runs`;
3. it prints the new state, then commits.

The repairs must run in the order above, and each `--apply` refuses to run until the previous one
has been applied:
- `editions` reads each match's day in Berlin time, which is only correct after repair 1.
- `finals` compares each final with the last match of its edition, which is only meaningful
  after repair 2.

`scripts/fix_qualifying_finals.py` is superseded by repair 3, and it has no dry run.

## 0. Preconditions

- [ ] Rafik has said "go" for this run.
- [ ] PR 2 (code fixes) is merged and deployed, and **ingestion is still paused**. The `daily-sync`,
  `upcoming-odds` and `rankings` cron jobs stay suspended until step 4.
- [ ] A backup exists and you know how to restore it:
  - Render dashboard → the Postgres instance → *Backups* / *Recovery*. Check what the current plan
    offers; free instances have no backups.
  - **and/or** a logical dump from a machine with PostgreSQL 16 client tools. These aren't
    installed on Rafik's laptop.

    ```bash
    pg_dump --format=custom --no-owner --file "tennis_data_$(date +%Y%m%d_%H%M).dump" "$DATABASE_URL"
    ```
- [ ] `DATABASE_URL` is set to the production database's **external** connection string, in your
  shell or `.env`. The script prints the host and database name before doing anything.
- [ ] This is a quiet moment. Repair 1 rewrites every row of `matches`: readers aren't blocked,
  but the transaction holds row locks until the commit.

Run everything from the repo root:

```bash
uv sync
uv run python scripts/repair_data.py --help
```

## 1. `scheduled_at` to UTC

```bash
uv run python scripts/repair_data.py scheduled-at-utc
```

What to check in the dry run:
- `a decaler` is close to the total number of matches (~110,700), split between `-2 h` and `-1 h`.
- `synchronises apres le cutoff` is **0**. If it isn't, ingestion ran after the freeze and the
  apply will refuse. Stop and work out which code wrote those rows. If they were written by the
  fixed code, rerun with `--cutoff <deploy time of PR 2>`.
- Sample match `32529` (2026 Wimbledon final) shows `2026-07-12 17:10Z -> 15:10Z`. Check one or
  two more matches with a known start time against an independent source, e.g. a night match at
  the 2026 US Open:

  ```bash
  uv run python scripts/repair_data.py scheduled-at-utc --sample-ids 32529,<id>,<id>
  ```

Then apply:

```bash
uv run python scripts/repair_data.py scheduled-at-utc --apply
```

## 2. Editions

```bash
uv run python scripts/repair_data.py editions
```

What to check in the dry run:
- The header says `jour d'un match lu dans le fuseau: Europe/Berlin`, which proves step 1 was applied.
- The 2026 US Open shows up as `move 87 matchs #423 US Open (atp) 2025 -> 2026 #2203`.
- Read the top list for anything surprising, such as a large `create` for a series you know is
  fine. `IGNORE (revue manuelle)` lines are inconsistent rows that the script leaves alone; note them.
- `[source videe]` marks a tournament row that will end up with no matches. It is reported, never deleted.

Then apply:

```bash
uv run python scripts/repair_data.py editions --apply
```

## 3. Finals

```bash
uv run python scripts/repair_data.py finals
```

What to check in the dry run:
- Tournament 2203 (2026 US Open, frozen at the QF stage) appears with its fake `F` labels demoted.
- Editions that finished long ago should mostly be absent. They were already right under the old
  rule. The exceptions are editions that had a stray match from another edition before step 2.

Then apply:

```bash
uv run python scripts/repair_data.py finals --apply
```

## 4. Verify, then resume

```bash
API=https://tennis-data-platform.onrender.com
curl -s "$API/matches/32529" | grep -o '"scheduled_at":"[^"]*"'           # 2026-07-12T15:10:00Z
curl -s "$API/matches?tournament_id=423&limit=200" | grep -o '"scheduled_at":"2026-' | wc -l   # 0
curl -s "$API/matches?tournament_id=2203&round_code=F&limit=1" | grep -o '"total":[0-9]*'   # "total":0
```

```sql
SELECT job_name, finished_at, rows_updated, error_message
FROM ingest_runs WHERE job_name LIKE 'repair:%' ORDER BY finished_at;   -- 3 rows
```

Only after that, and only if Rafik wants it, resume the cron jobs. They will now run the fixed code.

## Undo

- **Preferred:** restore the backup taken in step 0.
- Repair 1 alone, if nothing else has changed since: the inverse expression is
  `UPDATE matches SET scheduled_at = (scheduled_at AT TIME ZONE 'Europe/Berlin') AT TIME ZONE 'UTC'`,
  restricted to the same rows (`last_synced_at < cutoff`), then delete the `repair:scheduled_at_utc` marker.
  It is exact except for the one ambiguous hour per year when clocks go back.
- Repairs 2 and 3 have no automatic undo: restore the backup.
