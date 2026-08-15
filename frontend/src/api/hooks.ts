import { useQuery } from '@tanstack/react-query'
import { apiClient } from './client'
import type {
  H2HOut,
  MatchDetailOut,
  MatchFilters,
  MatchListOut,
  PlayerDetailOut,
  PlayerOut,
  RankingSnapshotOut,
  TournamentOut,
} from './types'

export function usePlayer(id: number | undefined) {
  return useQuery({
    queryKey: ['player', id],
    queryFn: async () => {
      const { data } = await apiClient.get<PlayerDetailOut>(`/players/${id}`)
      return data
    },
    enabled: id !== undefined,
  })
}

export function usePlayerSearch(q: string) {
  return useQuery({
    queryKey: ['player-search', q],
    queryFn: async () => {
      const { data } = await apiClient.get<PlayerOut[]>('/players', { params: { q } })
      return data
    },
    enabled: q.trim().length >= 2,
  })
}

export function useMatches(filters: MatchFilters) {
  return useQuery({
    queryKey: ['matches', filters],
    queryFn: async () => {
      const { data } = await apiClient.get<MatchListOut>('/matches', { params: filters })
      return data
    },
    placeholderData: (previous) => previous, // evite le flash "vide" en changeant de filtre
  })
}

export function useMatch(id: number | undefined) {
  return useQuery({
    queryKey: ['match', id],
    queryFn: async () => {
      const { data } = await apiClient.get<MatchDetailOut>(`/matches/${id}`)
      return data
    },
    enabled: id !== undefined,
  })
}

export function useTournaments(params: { season?: number; tour?: string; q?: string }) {
  return useQuery({
    queryKey: ['tournaments', params],
    queryFn: async () => {
      const { data } = await apiClient.get<TournamentOut[]>('/tournaments', { params })
      return data
    },
  })
}

export function usePlayerRankings(playerId: number | undefined, tour?: string) {
  return useQuery({
    queryKey: ['rankings', playerId, tour],
    queryFn: async () => {
      const { data } = await apiClient.get<RankingSnapshotOut[]>(`/players/${playerId}/rankings`, {
        params: { tour },
      })
      return data
    },
    enabled: playerId !== undefined,
  })
}

export function useH2H(playerId: number | undefined, otherPlayerId: number | undefined) {
  return useQuery({
    queryKey: ['h2h', playerId, otherPlayerId],
    queryFn: async () => {
      const { data } = await apiClient.get<H2HOut>(`/players/${playerId}/h2h/${otherPlayerId}`)
      return data
    },
    enabled: playerId !== undefined && otherPlayerId !== undefined,
  })
}
