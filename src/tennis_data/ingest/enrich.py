"""Petits enrichissements partages entre les scripts de backfill et de sync."""

from tennis_data.providers.api_tennis import ApiTennisClient


def build_surface_lookup(client: ApiTennisClient) -> dict[str, str]:
    print("Recuperation de get_tournaments pour enrichir la surface...")
    tournaments = client.get_tournaments()
    lookup = {
        str(t["tournament_key"]): t["tournament_sourface"]
        for t in tournaments
        if t.get("tournament_key") and t.get("tournament_sourface")
    }
    print(f"  {len(lookup)} tournois avec surface connue")
    return lookup
