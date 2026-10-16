"""
Reparation 2/4: matchs rattaches a la mauvaise edition (review 3.3).

La cle d'une edition est {tournament_key}_{saison}, et la saison venait du champ
tournament_season du fournisseur, pas fiable: ex. 87 matchs de l'US Open 2026 sous le
tournoi 423 (edition 2025) au lieu du 2203 (edition 2026). On recalcule la saison de
chaque match avec la regle de l'ingestion corrigee (ingest/seasons.py, jour du match a
Berlin) et on corrige chaque groupe (tournoi source, saison attendue):

- MOVE: l'edition de la bonne saison existe -> on y deplace les matchs
- RELABEL: tous les matchs du tournoi source changent de saison et personne d'autre ne
  vise ces cles -> on corrige la ligne elle-meme (season + cle externe)
- CREATE: sinon on cree l'edition manquante (copie nom/circuit/surface) et on y deplace
  les matchs

Les tournois source vides apres coup sont signales, jamais supprimes. Naturellement
idempotent: un 2e passage ne trouve plus rien a deplacer.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from sqlalchemy import func, text, update
from sqlalchemy.orm import Session

from tennis_data.ingest.mapping import PROVIDER_TZ, SOURCE
from tennis_data.ingest.seasons import season_for_date
from tennis_data.models import Match, Tournament, TournamentExternalId
from tennis_data.repairs import scheduled_at_utc
from tennis_data.repairs.markers import RepairRefused, applied_at, record_applied

NAME = "editions"

MOVE, RELABEL, CREATE = "move", "relabel", "create"


@dataclass
class EditionFix:
    action: str
    source_id: int
    source_name: str
    tour: str
    series_key: str
    source_season: int | None
    target_season: int
    match_ids: list[int]
    target_id: int | None = None  # MOVE vers une edition deja en base; None si creee par ce plan
    empties_source: bool = False  # le tournoi source n'aura plus aucun match (il reste en base)

    @property
    def target_external_id(self) -> str:
        return f"{self.series_key}_{self.target_season}"


@dataclass
class Plan:
    local_tz: str
    fixes: list[EditionFix] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # cas incoherents laisses a une revue manuelle

    @property
    def matches_reattached(self) -> int:
        return sum(len(f.match_ids) for f in self.fixes if f.action != RELABEL)

    def count(self, action: str) -> int:
        return sum(1 for f in self.fixes if f.action == action)


def _local_tz(session: Session) -> str:
    """Le jour d'un match se lit a Berlin, comme event_date. Tant que la reparation 1 n'est
    pas appliquee, scheduled_at contient deja l'heure de Berlin etiquetee UTC."""
    return PROVIDER_TZ.key if applied_at(session, scheduled_at_utc.NAME) else "UTC"


def plan(session: Session) -> Plan:
    local_tz = _local_tz(session)
    tournaments = {t.id: t for t in session.query(Tournament)}
    match_counts = dict(session.query(Match.tournament_id, func.count()).group_by(Match.tournament_id).all())
    tournament_by_external_id: dict[str, int] = {}
    external_ids_by_tournament: dict[int, list[str]] = defaultdict(list)
    for link in session.query(TournamentExternalId).filter_by(source=SOURCE):
        tournament_by_external_id[link.external_id] = link.tournament_id
        external_ids_by_tournament[link.tournament_id].append(link.external_id)

    groups: dict[tuple[int, int], list[int]] = defaultdict(list)
    rows = session.execute(
        text(
            "SELECT id, tournament_id, CAST(scheduled_at AT TIME ZONE :tz AS date) AS day "
            "FROM matches WHERE scheduled_at IS NOT NULL ORDER BY id"
        ),
        {"tz": local_tz},
    )
    for match_id, tournament_id, day in rows:
        season = season_for_date(day)
        if season != tournaments[tournament_id].season:
            groups[(tournament_id, season)].append(match_id)

    result = Plan(local_tz=local_tz)

    def series_key(t: Tournament) -> str | None:
        if t.external_series_key:
            return t.external_series_key
        own = external_ids_by_tournament[t.id]
        return own[0].rsplit("_", 1)[0] if len(own) == 1 else None

    targeted = Counter()
    for source_id, target_season in groups:
        key = series_key(tournaments[source_id])
        if key:
            targeted[f"{key}_{target_season}"] += 1

    claimed: set[str] = set()  # cles d'edition creees ou corrigees plus haut dans ce plan
    for (source_id, target_season), match_ids in sorted(groups.items()):
        source = tournaments[source_id]
        key = series_key(source)
        if key is None:
            result.skipped.append(f"tournoi {source_id} ({source.name}): cle de serie introuvable")
            continue
        fix = EditionFix(
            action=MOVE,
            source_id=source_id,
            source_name=source.name,
            tour=source.tour,
            series_key=key,
            source_season=source.season,
            target_season=target_season,
            match_ids=match_ids,
            empties_source=len(match_ids) == match_counts[source_id],
        )
        target_id = tournament_by_external_id.get(fix.target_external_id)
        own_external_id = f"{key}_{source.season}"

        if target_id is not None:
            if target_id == source_id or tournaments[target_id].season != target_season:
                result.skipped.append(
                    f"tournoi {source_id} ({source.name}): la cle {fix.target_external_id} pointe vers "
                    f"le tournoi {target_id} (saison {tournaments[target_id].season})"
                )
                continue
            fix.target_id = target_id
        elif fix.target_external_id in claimed:
            pass  # MOVE vers l'edition creee ou corrigee plus haut
        elif (
            fix.empties_source
            and targeted[fix.target_external_id] == 1
            and own_external_id not in targeted
            and external_ids_by_tournament[source_id] == [own_external_id]
        ):
            fix.action, fix.target_id, fix.empties_source = RELABEL, source_id, False
            claimed.add(fix.target_external_id)
        else:
            fix.action = CREATE
            claimed.add(fix.target_external_id)
        result.fixes.append(fix)

    return result


def apply(session: Session) -> Plan:
    """Applique le plan dans la transaction de l'appelant (qui commit) et laisse la trace."""
    if applied_at(session, scheduled_at_utc.NAME) is None:
        raise RepairRefused("appliquer d'abord la reparation scheduled-at-utc (le jour d'un match en depend)")

    result = plan(session)
    for fix in result.fixes:
        if fix.action == RELABEL:
            session.execute(update(Tournament).where(Tournament.id == fix.source_id).values(season=fix.target_season))
            session.execute(
                update(TournamentExternalId)
                .where(
                    TournamentExternalId.tournament_id == fix.source_id,
                    TournamentExternalId.source == SOURCE,
                    TournamentExternalId.external_id == f"{fix.series_key}_{fix.source_season}",
                )
                .values(external_id=fix.target_external_id)
            )
            continue

        if fix.action == CREATE:
            source = session.get(Tournament, fix.source_id)
            edition = Tournament(
                name=source.name,
                tour=source.tour,
                level=source.level,
                external_series_key=fix.series_key,
                surface=source.surface,
                country=source.country,
                city=source.city,
                season=fix.target_season,
            )
            session.add(edition)
            session.flush()
            session.add(
                TournamentExternalId(tournament_id=edition.id, source=SOURCE, external_id=fix.target_external_id)
            )
            session.flush()
            fix.target_id = edition.id
        elif fix.target_id is None:  # MOVE vers une edition creee ou corrigee plus haut
            fix.target_id = (
                session.query(TournamentExternalId.tournament_id)
                .filter_by(source=SOURCE, external_id=fix.target_external_id)
                .scalar()
            )

        session.execute(
            update(Match)
            .where(Match.id.in_(fix.match_ids), Match.tournament_id == fix.source_id)
            .values(tournament_id=fix.target_id)
        )

    record_applied(
        session,
        NAME,
        result.matches_reattached,
        note=f"{result.count(MOVE)} move, {result.count(RELABEL)} relabel, {result.count(CREATE)} create",
    )
    return result
