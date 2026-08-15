"""
Correction ponctuelle (deja executee une fois le 2026-08-13, gardee pour reference et
pour permettre une reverification manuelle a tout moment). La meme logique tourne
maintenant automatiquement a chaque daily_sync (voir tennis_data/ingest/maintenance.py).

Contexte: le champ event_qualification du fournisseur est absent (null) pour beaucoup
de matchs de qualifications plutot que d'etre correctement a False/True (confirme par
test: match ATP Australian Open 2022, M. Marterer vs T. Kamke, event_qualification=None).
Consequence: is_qualification restait a False par defaut, et le prefixe "Q-" ne
s'appliquait pas -> des finales de qualifs comptees comme "F" (vraie finale), gonflant
ce compte d'environ 2x.

Usage:
    python scripts/fix_qualifying_finals.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sqlalchemy import text

from tennis_data.db import get_session
from tennis_data.ingest.maintenance import reclassify_stale_qualifying_finals


def main():
    with get_session() as session:
        before = session.execute(text("select count(*) from matches where round_code = 'F'")).scalar()
        print(f"{before} matchs actuellement en round_code='F' (avant correction)")

        n_fixed = reclassify_stale_qualifying_finals(session)

        after = session.execute(text("select count(*) from matches where round_code = 'F'")).scalar()

    print(f"{n_fixed} matchs reclasses de 'F' vers 'Q-F' (finales de qualifs mal etiquetees)")
    print(f"{after} matchs restent en round_code='F' (vraies finales)")


if __name__ == "__main__":
    main()
