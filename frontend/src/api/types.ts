// Reflete src/tennis_data/api/schemas.py cote backend. Garder synchronise a la main
// (pas de generation automatique pour l'instant, le nombre d'endpoints est encore petit).

export interface PlayerOut {
  id: number
  full_name: string
  country_code: string | null
}

export interface PlayerDetailOut extends PlayerOut {
  birth_date: string | null
  hand: string | null
}

export interface TournamentOut {
  id: number
  name: string
  tour: string
  level: string | null
  surface: string | null
  country: string | null
  city: string | null
  season: number | null
}

export type MatchStatus =
  | 'scheduled'
  | 'live'
  | 'finished'
  | 'retired'
  | 'walkover'
  | 'cancelled'
  | 'postponed'

export interface MatchOut {
  id: number
  scheduled_at: string | null
  status: MatchStatus
  round_code: string | null
  round_raw: string | null
  score_raw: string | null
  is_qualification: boolean
  tournament: TournamentOut
  player1: PlayerOut | null
  player2: PlayerOut | null
  winner_id: number | null
}

export interface MatchListOut {
  total: number
  limit: number
  offset: number
  results: MatchOut[]
}

export interface SetOut {
  set_number: number
  player1_games: number | null
  player2_games: number | null
  tiebreak_player1_points: number | null
  tiebreak_player2_points: number | null
}

export interface StatisticOut {
  player_id: number
  stat_period: string
  stat_name: string
  stat_value: number | null
  stat_won: number | null
  stat_total: number | null
}

export interface OddsOut {
  bookmaker: string
  market: string
  selection: string
  odd_value: number
  captured_at: string
  is_retroactive: boolean
}

export interface MatchDetailOut extends MatchOut {
  sets: SetOut[]
  statistics: StatisticOut[]
  odds: OddsOut[]
}

export interface RankingSnapshotOut {
  tour: string
  snapshot_date: string
  rank: number | null
  points: number | null
  precision: 'weekly' | 'season_approx'
}

export interface H2HOut {
  player1: PlayerOut
  player2: PlayerOut
  player1_wins: number
  player2_wins: number
  matches: MatchOut[]
}

export interface SurfaceFormOut {
  surface: string
  matches: number
  wins: number
  win_rate: number | null
}

export interface PlayerFormOut {
  player_id: number
  as_of: string
  matches_considered: number
  matches_last_10: number
  win_rate_last_10: number | null
  matches_last_20: number
  win_rate_last_20: number | null
  matches_last_30: number
  win_rate_last_30: number | null
  matches_3m: number
  win_rate_3m: number | null
  matches_6m: number
  win_rate_6m: number | null
  matches_12m: number
  win_rate_12m: number | null
  by_surface: SurfaceFormOut[]
  streak_type: 'W' | 'L' | null
  streak_count: number
  days_since_last_match: number | null
  matches_last_30_days: number
}

export interface MatchFilters {
  date?: string
  date_from?: string
  date_to?: string
  tour?: string
  surface?: string
  round_code?: string
  status?: string
  tournament_id?: number
  player_id?: number
  q?: string
  limit?: number
  offset?: number
}
