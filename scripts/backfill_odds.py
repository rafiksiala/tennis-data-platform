"""
Backfill des cotes retroactives, dans la limite reellement confirmee par test le
2026-08-08: les cotes existent jusqu'a ~22-23 mois en arriere, plus rien au-dela.
On utilise 20 mois par securite (marge sous la limite exacte, qui peut varier legerement
selon les matchs/tournois).

Scope volontairement limite a ATP/WTA (pas Challenger): marches de paris moins liquides/
pertinents au niveau Challenger pour l'objectif produit, et ca limite le nombre d'appels
(1 appel = 1 match, contrairement aux fixtures qui sont chunkees).

Commit par lot de CHUNK_SIZE matchs (pas une seule transaction geante): si le processus
s'interrompt en cours de route (meme cause que le backfill de fixtures), on ne perd que
le lot en cours, et relancer le script reprend automatiquement la ou il s'est arrete
(la requete de candidats exclut deja les matchs qui ont des OddsSnapshot).

Usage:
    python scripts/backfill_odds.py
    python scripts/backfill_odds.py --months 20 --tours atp,wta
"""

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sqlalchemy import select

from tennis_data.db import get_session
from tennis_data.ingest.mapping import SOURCE, flatten_odds
from tennis_data.models import IngestRun, Match, MatchExternalId, OddsSnapshot, Tournament
from tennis_data.providers.api_tennis import ApiTennisClient, ApiTennisQuotaExceeded

CHUNK_SIZE = 50


def _log_run_safely(**kwargs) -> None:
    """Ecrit un IngestRun sans jamais faire planter l'appelant (une panne reseau
    transitoire peut aussi affecter CETTE ecriture juste apres l'echec initial)."""
    try:
        with get_session() as session:
            session.add(IngestRun(**kwargs))
    except Exception as log_exc:  # noqa: BLE001
        print(f"    (impossible d'ecrire l'IngestRun d'echec: {log_exc})")


def fetch_candidates(session, tours: list[str], cutoff: datetime) -> list[tuple[int, int]]:
    """Retourne (match.id, external_id) pour les matchs sans cotes. Requete refaite a
    chaque relance du script -> resumable naturellement (voir docstring du module)."""
    rows = (
        session.query(Match.id, MatchExternalId.external_id)
        .join(Tournament, Match.tournament_id == Tournament.id)
        .join(MatchExternalId, MatchExternalId.match_id == Match.id)
        .filter(Tournament.tour.in_(tours))
        .filter(Match.status == "finished")
        .filter(Match.scheduled_at >= cutoff)
        .filter(MatchExternalId.source == SOURCE)
        .filter(~Match.id.in_(select(OddsSnapshot.match_id).distinct()))
        .all()
    )
    return [(r[0], r[1]) for r in rows]


def process_chunk(client: ApiTennisClient, chunk: list[tuple[int, int]]) -> dict:
    """Une session par lot: si ca plante, seul ce lot est perdu, pas tout le run."""
    found, not_found, calls = 0, 0, 0
    with get_session() as session:
        run = IngestRun(job_name="backfill_odds")
        session.add(run)
        session.flush()

        for match_id, external_id in chunk:
            odds_dict = client.get_odds(int(external_id))
            calls += 1
            if odds_dict:
                for row in flatten_odds(odds_dict):
                    session.add(
                        OddsSnapshot(
                            match_id=match_id,
                            bookmaker=row["bookmaker"],
                            market=row["market"],
                            selection=row["selection"],
                            odd_value=row["value"],
                            captured_at=datetime.now(timezone.utc),
                            is_retroactive=True,
                            source=SOURCE,
                        )
                    )
                found += 1
            else:
                not_found += 1
            time.sleep(0.2)

        run.status = "success"
        run.finished_at = datetime.now(timezone.utc)
        run.rows_inserted = found
        run.api_calls_made = calls

    return {"found": found, "not_found": not_found, "calls": calls}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--months", type=int, default=20)
    parser.add_argument("--tours", default="atp,wta")
    args = parser.parse_args()
    tours = args.tours.split(",")

    client = ApiTennisClient()
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.months * 30)

    with get_session() as session:
        candidates = fetch_candidates(session, tours, cutoff)
    print(f"{len(candidates)} matchs sans cotes, dans la fenetre des {args.months} derniers mois")

    total_found, total_not_found, total_calls = 0, 0, 0
    for i in range(0, len(candidates), CHUNK_SIZE):
        chunk = candidates[i : i + CHUNK_SIZE]
        try:
            result = process_chunk(client, chunk)
        except ApiTennisQuotaExceeded as exc:
            print(f"\nQUOTA API EPUISE a {i}/{len(candidates)} matchs traites ({exc})")
            print("Arret propre. Relance le script plus tard (apres reset du quota, ou plan"
                  " superieur): il reprendra automatiquement la ou il s'est arrete.")
            break
        except Exception as exc:  # noqa: BLE001 - un lot en echec ne doit pas arreter le reste
            print(f"  lot {i}-{i+len(chunk)}: ECHEC ({exc}), on continue sur le suivant")
            _log_run_safely(
                job_name="backfill_odds",
                status="failed",
                finished_at=datetime.now(timezone.utc),
                error_message=str(exc)[:1000],
            )
            continue
        total_found += result["found"]
        total_not_found += result["not_found"]
        total_calls += result["calls"]
        print(
            f"  ... {i + len(chunk)}/{len(candidates)} traites "
            f"(trouve={total_found}, absent={total_not_found})"
        )

    print(f"Termine: {total_found} matchs avec cotes recuperees, {total_not_found} sans cotes "
          f"(trop anciens ou non couverts), {total_calls} appels API")


if __name__ == "__main__":
    main()
