import type { MatchStatus } from '../api/types'

const LABELS: Record<MatchStatus, string> = {
  scheduled: 'Scheduled',
  live: 'LIVE',
  finished: 'Finished',
  retired: 'Retired',
  walkover: 'W.O.',
  cancelled: 'Cancelled',
  postponed: 'Postponed',
}

const STYLES: Record<MatchStatus, string> = {
  scheduled: 'bg-slate-100 text-slate-600',
  live: 'bg-red-100 text-red-700 animate-pulse',
  finished: 'bg-slate-100 text-slate-500',
  retired: 'bg-amber-100 text-amber-700',
  walkover: 'bg-amber-100 text-amber-700',
  cancelled: 'bg-slate-100 text-slate-400',
  postponed: 'bg-slate-100 text-slate-400',
}

export function StatusBadge({ status }: { status: MatchStatus }) {
  return (
    <span className={`px-1.5 py-0.5 rounded text-[11px] font-medium whitespace-nowrap ${STYLES[status]}`}>
      {LABELS[status]}
    </span>
  )
}
