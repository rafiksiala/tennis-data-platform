"""
Client pour l'API API-Tennis (https://api-tennis.com/documentation).

Regroupe tout ce qui a ete confirme par test le 2026-08-08 (voir tennis-data-research/):
- les appels avec date_start/date_stop sont plafonnes a 7 jours par appel (non documente
  officiellement, confirme par l'erreur "Maximum date range for odds is 7 days" declenchee
  aussi sur get_fixtures) -> chunking automatique ici.
- get_players exige un player_key OU un tournament_key malgre une doc qui les dit optionnels.
- le format d'erreur de l'API est {"error": "1", "result": "message"} (pas de cle "success").
- les event_type_key ci-dessous ont ete recuperes via un vrai appel a get_events.
"""

import time
from datetime import datetime, timedelta
from typing import Any, Iterator

import requests

from tennis_data.config import API_TENNIS_KEY

BASE_URL = "https://api.api-tennis.com/tennis/"
MAX_DAYS_PER_CALL = 7

# Cles decouvertes par test le 2026-08-08 (voir tennis-data-research/results/get_events_*.json)
EVENT_TYPES = {
    "atp_singles": 265,
    "wta_singles": 266,
    "challenger_men_singles": 281,
    "challenger_women_singles": 272,
    "itf_men_singles": 270,
    "itf_women_singles": 271,
}


class ApiTennisError(Exception):
    pass


class ApiTennisQuotaExceeded(ApiTennisError):
    """Quota journalier/mensuel epuise: inutile de retenter, il faut attendre le
    reset ou changer de plan. Detecte le 2026-08-09 lors du backfill des cotes."""

    pass


class ApiTennisClient:
    def __init__(self, api_key: str | None = None, max_retries: int = 3):
        self.api_key = api_key or API_TENNIS_KEY
        if not self.api_key:
            raise ApiTennisError("API_TENNIS_KEY manquante (voir .env.example)")
        self.max_retries = max_retries

    def _call(self, method: str, **params: Any) -> dict:
        query = {"method": method, "APIkey": self.api_key, **params}
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.get(BASE_URL, params=query, timeout=60)
                resp.raise_for_status()
                data = resp.json()
                if data.get("error"):
                    message = str(data.get("result"))
                    if "limit exceeded" in message.lower() or "upgrade your plan" in message.lower():
                        raise ApiTennisQuotaExceeded(f"{method} -> {message}")
                    raise ApiTennisError(f"{method} -> {message}")
                return data
            except ApiTennisQuotaExceeded:
                raise  # pas la peine de retenter, ni ici ni dans l'appelant
            except (requests.RequestException, ApiTennisError, ValueError) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)  # backoff exponentiel: 2s, 4s, 8s...
        raise ApiTennisError(f"echec apres {self.max_retries} tentatives sur {method}: {last_exc}") from last_exc

    @staticmethod
    def _date_chunks(date_start: str, date_stop: str, max_days: int = MAX_DAYS_PER_CALL) -> Iterator[tuple[str, str]]:
        start = datetime.strptime(date_start, "%Y-%m-%d").date()
        stop = datetime.strptime(date_stop, "%Y-%m-%d").date()
        cur = start
        while cur <= stop:
            chunk_end = min(cur + timedelta(days=max_days - 1), stop)
            yield str(cur), str(chunk_end)
            cur = chunk_end + timedelta(days=1)

    def get_events(self) -> list[dict]:
        return self._call("get_events").get("result", [])

    def get_tournaments(self) -> list[dict]:
        return self._call("get_tournaments").get("result", [])

    def get_fixtures_range(self, date_start: str, date_stop: str, **extra_params: Any) -> list[dict]:
        """Recupere get_fixtures sur une plage arbitraire, decoupee automatiquement en
        fenetres de 7 jours max. Retourne la liste combinee des matchs."""
        all_matches: list[dict] = []
        for cs, ce in self._date_chunks(date_start, date_stop):
            data = self._call("get_fixtures", date_start=cs, date_stop=ce, **extra_params)
            all_matches.extend(data.get("result", []) or [])
        return all_matches

    def get_livescore(self, **extra_params: Any) -> list[dict]:
        return self._call("get_livescore", **extra_params).get("result", [])

    def get_odds(self, match_key: int) -> dict | None:
        """Retourne le dict de cotes pour ce match, ou None si aucune cote disponible.
        Profondeur reelle confirmee par test: ~22-23 mois. Au-dela, retourne None."""
        data = self._call("get_odds", match_key=match_key)
        result = data.get("result", {})
        return result.get(str(match_key)) or result.get(match_key)

    def get_players(self, *, player_key: int | None = None, tournament_key: int | None = None) -> list[dict]:
        if not player_key and not tournament_key:
            raise ApiTennisError("get_players exige player_key ou tournament_key (confirme par test)")
        params = {}
        if player_key:
            params["player_key"] = player_key
        if tournament_key:
            params["tournament_key"] = tournament_key
        return self._call("get_players", **params).get("result", [])

    def get_h2h(self, first_player_key: int, second_player_key: int) -> dict:
        data = self._call("get_H2H", first_player_key=first_player_key, second_player_key=second_player_key)
        return data.get("result", {})

    def get_standings(self, tour: str) -> list[dict]:
        """tour: 'ATP' ou 'WTA'. Snapshot courant uniquement (pas d'historique via cet endpoint)."""
        return self._call("get_standings", event_type=tour).get("result", [])
