"""
Reparations ponctuelles des lignes deja en base (octobre 2026), a lancer via
scripts/repair_data.py, dans l'ordre:

1. scheduled_at_utc: heures de Berlin stockees comme de l'UTC -> vrai UTC (ADR-0003)
2. editions: matchs rattaches a la mauvaise edition (saison du fournisseur fausse)
3. finals: reetiquetage F / Q-F avec la regle "la vraie finale est le dernier match"

Chaque module expose preview() (lecture seule) et apply() (ecrit, dans la transaction de
l'appelant). Chaque apply() reussi laisse une trace dans ingest_runs (job_name
'repair:<nom>', voir markers.py), qui sert de garde-fou: ordre impose et pas de double
application. Mode d'emploi: docs/runbooks/data-repair-2026-10.md.
"""
