"""
Conversions d'heures vers UTC (ADR-0003: tout est stocke et compare en UTC).

Deux cas seulement:
- une heure "murale" d'un fuseau connu (ex: heure de Berlin renvoyee par le fournisseur)
  -> wall_time_to_utc
- une entree sans fuseau (ex: parametre as_of de l'API) -> as_utc la considere comme UTC
"""

from datetime import datetime, timezone


def wall_time_to_utc(local: datetime) -> datetime:
    """`local` porte le fuseau voulu dans tzinfo (son `fold` est ignore). Retourne l'instant UTC.

    Aux changements d'heure, une heure murale peut etre ambigue (passage a l'heure d'hiver:
    02:30 existe deux fois) ou inexistante (passage a l'heure d'ete: 02:30 n'existe pas).
    Dans les deux cas on retient l'heure d'hiver (standard), exactement comme Postgres le
    fait pour `timestamp AT TIME ZONE '<zone>'`: l'ingestion et le script de reparation
    SQL des lignes existantes donnent ainsi le meme instant (verifie par
    tests/test_timeutil.py contre Postgres)."""
    first, second = local.replace(fold=0), local.replace(fold=1)
    if first.utcoffset() != second.utcoffset():
        local = first if not first.dst() else second
    return local.astimezone(timezone.utc)


def as_utc(value: datetime) -> datetime:
    """Datetime sans fuseau -> considere comme UTC; avec fuseau -> converti en UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
