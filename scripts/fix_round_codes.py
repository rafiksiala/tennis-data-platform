"""
Correction ponctuelle: recalcule matches.round_code a partir de round_raw + is_qualification
(deja en base, pas besoin de rappeler l'API), suite a DEUX bugs de mapping corriges:
1. (2026-08-12) "1/8-finals" etc. incorrectement classes "F" a cause de l'ordre des mots-cles.
2. (2026-08-13) les finales de QUALIFICATIONS (meme libelle brut "Final" que la vraie
   finale du tournoi) n'etaient pas distinguees -> gonflait massivement le compte de "F"
   (ex: "Australian Open - Final" trouve 136 fois, alors qu'il y a ~1 vraie finale/an).

A lancer une seule fois. Sans danger a relancer (idempotent: recalcule juste la meme
valeur si round_raw/is_qualification n'ont pas change) - utile si une coupure reseau
interrompt un run, il suffit de relancer, ca reprend depuis le debut mais va vite sur
les lignes deja bonnes.

Usage:
    python scripts/fix_round_codes.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sqlalchemy import text

from tennis_data.db import get_session
from tennis_data.ingest.mapping import normalize_round
from tennis_data.models import Match

BATCH_SIZE = 2000
MAX_ATTEMPTS = 3


def process_batch(last_id: int) -> tuple[int, int, int | None]:
    """Retourne (nb_verifies, nb_corriges, dernier_id_traite). dernier_id_traite=None
    quand il n'y a plus rien a traiter."""
    with get_session() as session:
        batch = (
            session.query(Match.id, Match.round_raw, Match.round_code, Match.is_qualification)
            .filter(Match.round_raw.isnot(None), Match.id > last_id)
            .order_by(Match.id)
            .limit(BATCH_SIZE)
            .all()
        )
        if not batch:
            return 0, 0, None

        updates = []
        for match_id, round_raw, current_code, is_qualification in batch:
            new_code, _ = normalize_round(round_raw, is_qualification)
            if new_code != current_code:
                updates.append({"id": match_id, "round_code": new_code})

        if updates:
            session.bulk_update_mappings(Match, updates)

        return len(batch), len(updates), batch[-1][0]


def main():
    with get_session() as session:
        total = session.execute(text("select count(*) from matches where round_raw is not null")).scalar()
    print(f"{total} matchs avec un round_raw a reverifier")

    fixed, checked, last_id = 0, 0, 0
    while True:
        last_exc = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                n_checked, n_fixed, new_last_id = process_batch(last_id)
                last_exc = None
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                print(f"  lot apres id={last_id}: tentative {attempt}/{MAX_ATTEMPTS} echouee ({exc})")
                if attempt < MAX_ATTEMPTS:
                    time.sleep(5 * attempt)

        if last_exc is not None:
            print(f"ECHEC DEFINITIF apres {MAX_ATTEMPTS} tentatives sur le lot apres id={last_id}. "
                  f"Relance le script: il reprendra depuis le debut (idempotent, rapide sur le deja-bon).")
            break

        if new_last_id is None:
            break

        checked += n_checked
        fixed += n_fixed
        last_id = new_last_id
        print(f"  ... {checked}/{total} verifies, {fixed} corrections appliquees jusqu'ici")

    print(f"Termine: {fixed} matchs corriges sur {checked} verifies")


if __name__ == "__main__":
    main()
