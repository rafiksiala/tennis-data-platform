"""Petits enrichissements partages entre les scripts de backfill et de sync."""

from tennis_data.providers.api_tennis import ApiTennisClient

# Le champ tournament_sourface du fournisseur contient parfois un libelle de phase
# d'equipe (Coupe Davis: "- Preliminary", "- Play Offs", "- Qualification", etc.) au
# lieu d'une vraie surface - trouve par test le 2026-08-15 en construisant les
# indicateurs de forme (une pseudo-surface "- Play Offs" polluait le win rate par
# surface). Filtre positif: on n'accepte que ce qui contient un mot-cle de surface
# reelle, tout le reste devient NULL plutot que de stocker une valeur fausse.
VALID_SURFACE_KEYWORDS = ("hard", "clay", "grass", "carpet")


def _normalize_surface(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = raw.strip()
    if not any(kw in cleaned.lower() for kw in VALID_SURFACE_KEYWORDS):
        return None
    # normalise la casse: "clay" et "Clay" ne doivent pas devenir deux surfaces distinctes
    return cleaned.title()


def build_surface_lookup(client: ApiTennisClient) -> dict[str, str]:
    print("Recuperation de get_tournaments pour enrichir la surface...")
    tournaments = client.get_tournaments()
    lookup = {}
    for t in tournaments:
        surface = _normalize_surface(t.get("tournament_sourface"))
        if t.get("tournament_key") and surface:
            lookup[str(t["tournament_key"])] = surface
    print(f"  {len(lookup)} tournois avec surface valide connue")
    return lookup
