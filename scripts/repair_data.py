"""
Reparations des donnees existantes (octobre 2026). PAR DEFAUT: SIMULATION, rien n'est ecrit.

A lancer dans cet ordre (chaque etape refuse de s'appliquer si la precedente ne l'a pas ete):
    python scripts/repair_data.py scheduled-at-utc   # 1. heures de Berlin -> vrai UTC
    python scripts/repair_data.py editions           # 2. matchs rattaches a la bonne edition
    python scripts/repair_data.py finals             # 3. reetiquetage F / Q-F

Ajouter --apply pour ecrire (une seule transaction, confirmation demandee). Mode d'emploi
complet, sauvegarde prealable et requetes de verification: docs/runbooks/data-repair-2026-10.md.

NE PAS LANCER --apply sans le feu vert explicite de Rafik et une sauvegarde fraiche.
"""

import argparse
import sys
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from tennis_data.db import engine
from tennis_data.repairs import editions, finals, scheduled_at_utc
from tennis_data.repairs.markers import RepairRefused
from tennis_data.timeutil import as_utc

TOP = 25  # lignes de detail affichees


def _show_scheduled_at_utc(session: Session, args) -> None:
    p = scheduled_at_utc.preview(session, cutoff=args.cutoff, sample_ids=args.sample_ids)
    if p.already_applied_at:
        # les compteurs "a decaler" n'ont plus de sens: on montre juste les heures actuelles
        print(f"DEJA APPLIQUEE le {p.already_applied_at:%Y-%m-%d %H:%M} UTC")
        for s in p.samples:
            print(f"  match {s['id']}: {s['stored']:%Y-%m-%d %H:%M}Z")
        return
    print(f"cutoff (lignes synchronisees avant): {p.cutoff.isoformat()}")
    print(f"matchs avec une heure:         {p.matches_with_time}")
    print(f"a decaler:                     {p.to_shift}  (-2 h: {p.shift_2h}, -1 h: {p.shift_1h})")
    print(f"synchronises apres le cutoff:  {p.synced_after_cutoff}  (laisses tels quels)")
    for s in p.samples:
        print(f"  match {s['id']}: {s['stored']:%Y-%m-%d %H:%M}Z -> {s['repaired']:%Y-%m-%d %H:%M}Z", end="")
        print("" if s["will_shift"] else "  (non concerne)")


def _show_editions(session: Session, args) -> None:
    plan = editions.plan(session)
    print(f"jour d'un match lu dans le fuseau: {plan.local_tz}")
    print(
        f"{plan.matches_reattached} matchs a rattacher: {plan.count(editions.MOVE)} move, "
        f"{plan.count(editions.CREATE)} create, {plan.count(editions.RELABEL)} relabel"
    )
    for fix in sorted(plan.fixes, key=lambda f: -len(f.match_ids))[:TOP]:
        target = f"#{fix.target_id}" if fix.target_id else "(nouvelle edition)"
        empty = "  [source videe]" if fix.empties_source else ""
        print(
            f"  {fix.action:7} {len(fix.match_ids):4} matchs  #{fix.source_id} {fix.source_name} ({fix.tour}) "
            f"{fix.source_season} -> {fix.target_season} {target}{empty}"
        )
    if len(plan.fixes) > TOP:
        print(f"  ... {len(plan.fixes) - TOP} autres")
    for reason in plan.skipped:
        print(f"  IGNORE (revue manuelle): {reason}")


def _show_finals(session: Session, args) -> None:
    rows = finals.preview(session)
    demoted, promoted = sum(r["demoted"] for r in rows), sum(r["promoted"] for r in rows)
    print(f"{demoted} F -> Q-F, {promoted} Q-F -> F, sur {len(rows)} editions")
    for r in sorted(rows, key=lambda r: -(r["demoted"] + r["promoted"]))[:TOP]:
        print(f"  #{r['tournament_id']} {r['name']} ({r['tour']} {r['season']}): -{r['demoted']} F, +{r['promoted']} F")


def _apply(session: Session, args) -> None:
    if args.repair == "scheduled-at-utc":
        n = scheduled_at_utc.apply(session, cutoff=args.cutoff, cutoff_is_explicit=args.cutoff_is_explicit)
        print(f"{n} matchs decales")
    elif args.repair == "editions":
        plan = editions.apply(session)
        print(f"{plan.matches_reattached} matchs rattaches ({len(plan.fixes)} corrections)")
    else:
        result = finals.apply(session)
        print(f"{result.demoted} F -> Q-F, {result.promoted} Q-F -> F")


SHOW = {"scheduled-at-utc": _show_scheduled_at_utc, "editions": _show_editions, "finals": _show_finals}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("repair", choices=list(SHOW))
    parser.add_argument("--apply", action="store_true", help="ecrire (sinon simulation en lecture seule)")
    parser.add_argument("--yes", action="store_true", help="ne pas demander de confirmation (avec --apply)")
    parser.add_argument(
        "--cutoff",
        type=lambda v: as_utc(datetime.fromisoformat(v)),
        help="scheduled-at-utc: ne decaler que les lignes synchronisees avant cet instant "
        f"(defaut {scheduled_at_utc.DEFAULT_CUTOFF.isoformat()}, lendemain du gel)",
    )
    parser.add_argument(
        "--sample-ids",
        type=lambda v: [int(x) for x in v.split(",") if x],
        default=list(scheduled_at_utc.DEFAULT_SAMPLE_IDS),
        help="scheduled-at-utc: matchs a afficher avant/apres (ex: 32529,1234)",
    )
    args = parser.parse_args()
    args.cutoff_is_explicit = args.cutoff is not None
    args.cutoff = args.cutoff or scheduled_at_utc.DEFAULT_CUTOFF

    url = engine.url
    print(f"base: {url.host}:{url.port}/{url.database} (utilisateur {url.username})")
    print(f"reparation: {args.repair} - {'APPLICATION' if args.apply else 'simulation, lecture seule'}\n")

    with Session(engine) as session:
        if not args.apply:
            session.execute(text("SET TRANSACTION READ ONLY"))  # la simulation ne peut rien ecrire
        session.execute(text("SET LOCAL lock_timeout = '10s'"))
        session.execute(text("SET LOCAL statement_timeout = '15min'"))

        SHOW[args.repair](session, args)
        if not args.apply:
            session.rollback()
            print("\nSimulation terminee, rien n'a ete ecrit. Relancer avec --apply pour appliquer.")
            return 0

        if not args.yes:
            answer = input(f"\nAppliquer sur la base '{url.database}' de {url.host} ? Taper son nom pour confirmer: ")
            if answer.strip() != url.database:
                session.rollback()
                print("Annule, rien n'a ete ecrit.")
                return 1
        try:
            _apply(session, args)
        except RepairRefused as exc:
            session.rollback()
            print(f"REFUSE: {exc}\nRien n'a ete ecrit.")
            return 2
        print("\nEtat apres application (avant commit):")
        SHOW[args.repair](session, args)
        session.commit()
        print("\nCommitte.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
