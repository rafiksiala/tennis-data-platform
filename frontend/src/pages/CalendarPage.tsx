import { useMemo, useState } from 'react'
import { useMatches } from '../api/hooks'
import { FilterBar } from '../components/FilterBar'
import { TournamentGroup } from '../components/TournamentGroup'
import { PlayerSearch } from '../components/PlayerSearch'
import { toDateStr } from '../lib/date'
import type { MatchOut } from '../api/types'

function groupByTournament(matches: MatchOut[]): MatchOut[][] {
  const order: number[] = []
  const groups = new Map<number, MatchOut[]>()
  for (const m of matches) {
    if (!groups.has(m.tournament.id)) {
      groups.set(m.tournament.id, [])
      order.push(m.tournament.id)
    }
    groups.get(m.tournament.id)!.push(m)
  }
  return order.map((id) => groups.get(id)!)
}

export function CalendarPage() {
  const [date, setDate] = useState(toDateStr(new Date()))
  const [tour, setTour] = useState('')
  const [status, setStatus] = useState('')

  const { data, isLoading, isError, isPlaceholderData } = useMatches({
    date,
    tour: tour || undefined,
    status: status || undefined,
    limit: 200,
  })

  const groups = useMemo(() => groupByTournament(data?.results ?? []), [data])

  return (
    <div className="max-w-3xl mx-auto px-4 py-6">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold text-slate-900">Tennis — Schedule &amp; Results</h1>
        <PlayerSearch />
      </div>

      <FilterBar
        date={date}
        onDateChange={setDate}
        tour={tour}
        onTourChange={setTour}
        status={status}
        onStatusChange={setStatus}
      />

      {isLoading && <p className="text-slate-500 text-sm">Loading…</p>}
      {isError && <p className="text-red-600 text-sm">Error loading matches.</p>}
      {!isLoading && !isError && groups.length === 0 && (
        <p className="text-slate-500 text-sm">No matches for these filters.</p>
      )}

      <div className={isPlaceholderData ? 'opacity-60 transition-opacity' : ''}>
        {groups.map((g) => (
          <TournamentGroup key={g[0].tournament.id} matches={g} />
        ))}
      </div>

      {data && data.total > (data.results.length + data.offset) && (
        <p className="text-xs text-slate-400 text-center mt-2">
          Showing {data.results.length} of {data.total} matches
        </p>
      )}
    </div>
  )
}
