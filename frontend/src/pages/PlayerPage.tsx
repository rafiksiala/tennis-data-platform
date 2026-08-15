import { useParams, Link } from 'react-router-dom'
import { usePlayer, usePlayerRankings, useMatches } from '../api/hooks'
import { countryFlag } from '../lib/countries'
import { MatchRow } from '../components/MatchRow'
import type { RankingSnapshotOut } from '../api/types'

function age(birthDate: string | null): number | null {
  if (!birthDate) return null
  const diff = Date.now() - new Date(birthDate).getTime()
  return Math.floor(diff / (365.25 * 24 * 3600 * 1000))
}

export function PlayerPage() {
  const { id } = useParams()
  const playerId = id ? Number(id) : undefined

  const { data: player, isLoading, isError } = usePlayer(playerId)
  const { data: rankings } = usePlayerRankings(playerId)
  const { data: matches } = useMatches({ player_id: playerId, limit: 20 })

  if (isLoading) return <div className="max-w-2xl mx-auto px-4 py-6 text-slate-500 text-sm">Loading…</div>
  if (isError || !player)
    return <div className="max-w-2xl mx-auto px-4 py-6 text-red-600 text-sm">Player not found.</div>

  const latestByTour = new Map<string, RankingSnapshotOut>()
  for (const r of rankings ?? []) {
    if (!latestByTour.has(r.tour)) latestByTour.set(r.tour, r)
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-6">
      <Link to="/" className="text-sm text-blue-700 hover:underline mb-4 inline-block">
        ← Back to schedule
      </Link>

      <div className="bg-white border border-slate-200 rounded-lg p-4 mb-4">
        <h1 className="text-lg font-bold text-slate-900 mb-2">
          {countryFlag(player.country_code)} {player.full_name}
        </h1>
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-slate-600">
          {player.country_code && <span>{player.country_code}</span>}
          {player.birth_date && (
            <span>
              Born {new Date(player.birth_date).toLocaleDateString('en-US')} (age {age(player.birth_date)})
            </span>
          )}
          {!player.country_code && !player.birth_date && (
            <span className="text-slate-400">No biographical data available yet</span>
          )}
        </div>

        {latestByTour.size > 0 && (
          <div className="flex gap-4 mt-3 pt-3 border-t border-slate-100">
            {[...latestByTour.entries()].map(([tour, r]) => (
              <div key={tour} className="text-sm">
                <span className="text-xs uppercase text-slate-400">{tour}</span>{' '}
                <span className="font-semibold text-slate-900">#{r.rank}</span>
                <span className="text-slate-400"> ({r.points} pts)</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <h2 className="text-sm font-semibold text-slate-800 px-3 py-2 bg-slate-50 border-b border-slate-200">
          Recent matches
        </h2>
        {matches && matches.results.length > 0 ? (
          matches.results.map((m) => <MatchRow key={m.id} match={m} />)
        ) : (
          <p className="text-sm text-slate-400 px-3 py-3">No recent matches found.</p>
        )}
      </div>
    </div>
  )
}
