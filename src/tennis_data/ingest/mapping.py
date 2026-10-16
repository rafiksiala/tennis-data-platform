"""
Normalisation des donnees brutes API-Tennis vers notre vocabulaire interne.

Toute la connaissance specifique au format API-Tennis vit ici et nulle part ailleurs.
Si on change/ajoute un fournisseur un jour, on ecrit un module mapping equivalent pour
lui, et le reste du pipeline (upsert, analytics) n'a rien a savoir de la difference.
"""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from tennis_data.ingest.seasons import season_for_date
from tennis_data.timeutil import wall_time_to_utc

SOURCE = "api_tennis"

# Sans parametre `timezone` dans la requete (on n'en passe pas), API-Tennis renvoie
# event_date/event_time en heure de Berlin (doc officielle), PAS en UTC. Avant le
# 2026-10-16 ces heures etaient stockees telles quelles comme si c'etait de l'UTC
# (1 a 2 h de decalage, voir docs/adr/0003-utc-timestamps.md).
PROVIDER_TZ = ZoneInfo("Europe/Berlin")

STATUS_MAP = {
    "finished": "finished",
    "retired": "retired",
    "walkover": "walkover",
    "walk over": "walkover",
    "w.o.": "walkover",
    "cancelled": "cancelled",
    "canceled": "cancelled",
    "postponed": "postponed",
    "abandoned": "cancelled",
}


def normalize_status(event_status: str | None) -> tuple[str, str | None]:
    """Retourne (status_normalise, status_brut). Tout ce qui n'est pas explicitement
    fini/retire/walkover/annule/reporte et qui n'est pas un score de set (ex: 'Set 2')
    est considere 'live' si un score existe, sinon 'scheduled'."""
    raw = event_status or ""
    key = raw.strip().lower()
    if key in STATUS_MAP:
        return STATUS_MAP[key], raw
    if key.startswith("set "):
        return "live", raw
    if key in ("", "not started"):
        return "scheduled", raw
    return "live", raw  # valeur inconnue -> on suppose "en cours" plutot que de planter


# Mots-cles observes dans tournament_round (ex: "ATP Wimbledon - 1/8-finals").
# ATTENTION A L'ORDRE: "1/8-finals", "quarterfinals" et "semifinals" contiennent tous
# la sous-chaine "final" -> "final" doit etre verifie EN DERNIER, sinon un match de
# 1/8 de finale est incorrectement classe comme une Finale (bug reel trouve par test
# le 2026-08-12, corrige avec un script de reparation des donnees deja en base).
ROUND_KEYWORDS = [
    ("round robin", "RR"),
    ("1/64", "R128"),
    ("1/32", "R64"),
    ("1/16", "R32"),
    ("1/8", "R16"),
    ("quarter", "QF"),
    ("semi", "SF"),
    ("final", "F"),
]


def normalize_round(tournament_round: str | None, is_qualification: bool = False) -> tuple[str | None, str | None]:
    """Retourne (round_code, round_raw). round_code est None si aucun mot-cle connu
    n'est trouve - mieux vaut NULL qu'une valeur fausse.

    is_qualification prefixe le code avec "Q-": le fournisseur utilise le MEME libelle
    "Final" pour la vraie finale du tournoi ET pour le dernier tour des qualifications
    (bug reel trouve par test le 2026-08-13: des centaines de matchs de qualifs du 1er
    tour du tableau, joues 2 semaines avant la vraie finale, etaient comptes comme "F").
    Sans le prefixe, "Q-F" (dernier tour de qualifs) serait indiscernable de "F" (vraie
    finale) alors que ce sont des contextes tres differents pour l'analyse."""
    raw = tournament_round
    if not raw:
        return None, raw
    lowered = raw.lower()
    for keyword, code in ROUND_KEYWORDS:
        if keyword in lowered:
            return (f"Q-{code}" if is_qualification else code), raw
    return None, raw


# Mapping stat_name brut (tel que renvoye par get_fixtures) -> nom canonique.
# Construit a partir d'un echantillon reel (voir tennis-data-research/results/).
# Toute cle absente de ce dict est sluggifiee automatiquement (voir normalize_stat_name)
# plutot que de faire planter l'ingestion - a ajouter ici au fur et a mesure qu'on les rencontre.
STAT_NAME_MAP = {
    "Aces": "aces",
    "Double Faults": "double_faults",
    "1st serve percentage": "first_serve_pct",
    "1st serve points won": "first_serve_points_won_pct",
    "2nd serve points won": "second_serve_points_won_pct",
    "Break Points Saved": "break_points_saved_pct",
    "1st return points won": "first_return_points_won_pct",
    "2nd return points won": "second_return_points_won_pct",
    "Break Points Converted": "break_points_converted_pct",
    "Winners": "winners",
    "Unforced errors": "unforced_errors",
    "Net points won": "net_points_won_pct",
    "Service Points Won": "service_points_won_pct",
    "Return Points Won": "return_points_won_pct",
}


def normalize_stat_name(raw_name: str) -> str:
    if raw_name in STAT_NAME_MAP:
        return STAT_NAME_MAP[raw_name]
    return raw_name.strip().lower().replace(" ", "_").replace("%", "pct")


def parse_stat_value(raw_value: str | None) -> float | None:
    if raw_value is None:
        return None
    cleaned = str(raw_value).strip().rstrip("%")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_event_datetime(event_date: str | None, event_time: str | None) -> datetime | None:
    """event_date ("YYYY-MM-DD") + event_time ("HH:MM"), en heure de Berlin -> instant UTC
    (datetime aware). Sans heure, minuit heure de Berlin (comme avant). None si la date
    manque ou est illisible."""
    if not event_date:
        return None
    try:
        local = datetime.strptime(f"{event_date} {event_time or '00:00'}", "%Y-%m-%d %H:%M").replace(tzinfo=PROVIDER_TZ)
    except ValueError:
        return None
    return wall_time_to_utc(local)


def fixture_season(fixture: dict) -> int:
    """Saison de l'edition a laquelle rattacher le match: deduite de event_date (date du
    match a Berlin), car tournament_season n'est pas fiable (voir seasons.py). Repli sur
    tournament_season si la date manque, puis sur l'annee en cours."""
    raw_date = fixture.get("event_date")
    if raw_date:
        try:
            return season_for_date(date.fromisoformat(raw_date))
        except ValueError:
            pass
    try:
        season = int(fixture.get("tournament_season") or 0)
    except (TypeError, ValueError):
        season = 0
    return season or datetime.now(timezone.utc).year


def flatten_odds(odds_dict: dict) -> list[dict]:
    """Aplati la structure imbriquee {marche: {selection: {bookmaker: valeur}}}
    renvoyee par get_odds en une liste de lignes (market, selection, bookmaker, value)."""
    rows = []
    for market, selections in (odds_dict or {}).items():
        if not isinstance(selections, dict):
            continue
        for selection, bookmakers in selections.items():
            if not isinstance(bookmakers, dict):
                continue
            for bookmaker, value in bookmakers.items():
                parsed = parse_stat_value(value)
                if parsed is not None:
                    rows.append({"market": market, "selection": selection, "bookmaker": bookmaker, "value": parsed})
    return rows


def parse_score_component(raw: str | None) -> tuple[int | None, int | None]:
    """API-Tennis encode parfois un tie-break dans le score de jeux avec un point
    decimal (ex: "6.4" = 6 jeux, tie-break termine avec ce joueur a 4 points), observe
    sur un echantillon le 2026-08-08. Retourne (jeux, points_tiebreak).
    A RE-VERIFIER sur un plus grand echantillon avant de considerer cette interpretation
    definitive - en attendant, score_raw est toujours conserve tel quel en parallele."""
    if raw is None:
        return None, None
    text = str(raw)
    if "." in text:
        games_part, tb_part = text.split(".", 1)
        try:
            return int(games_part), int(tb_part)
        except ValueError:
            return None, None
    try:
        return int(text), None
    except ValueError:
        return None, None
