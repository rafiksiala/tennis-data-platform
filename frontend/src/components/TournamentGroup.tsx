import type { MatchOut } from '../api/types'
import { MatchRow } from './MatchRow'

const TOUR_LABELS: Record<string, string> = {
  atp: 'ATP',
  wta: 'WTA',
  challenger_men: 'Challenger H',
  challenger_women: 'Challenger F',
  itf_men: 'ITF H',
  itf_women: 'ITF F',
}

export function TournamentGroup({ matches }: { matches: MatchOut[] }) {
  if (matches.length === 0) return null
  const { tournament } = matches[0]

  return (
    <div className="mb-3 rounded-lg border border-slate-200 bg-white overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-2 bg-slate-50 border-b border-slate-200">
        <span className="text-[11px] font-semibold uppercase text-blue-700">
          {TOUR_LABELS[tournament.tour] ?? tournament.tour}
        </span>
        <span className="text-sm font-medium text-slate-800">{tournament.name}</span>
        {tournament.surface && <span className="text-xs text-slate-400">· {tournament.surface}</span>}
      </div>
      <div>
        {matches.map((m) => (
          <MatchRow key={m.id} match={m} />
        ))}
      </div>
    </div>
  )
}
