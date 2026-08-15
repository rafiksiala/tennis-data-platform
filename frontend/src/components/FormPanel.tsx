import type { PlayerFormOut } from '../api/types'

function pct(rate: number | null): string {
  return rate === null ? '-' : `${Math.round(rate * 100)}%`
}

function StatTile({ label, rate, matches }: { label: string; rate: number | null; matches: number }) {
  return (
    <div className="text-center">
      <div className="text-lg font-bold text-slate-900">{pct(rate)}</div>
      <div className="text-[11px] text-slate-400">
        {label} ({matches})
      </div>
    </div>
  )
}

export function FormPanel({ form }: { form: PlayerFormOut }) {
  if (form.matches_considered === 0) {
    return (
      <div className="bg-white border border-slate-200 rounded-lg p-4 mb-4">
        <p className="text-sm text-slate-400">No completed matches on record yet.</p>
      </div>
    )
  }

  return (
    <div className="bg-white border border-slate-200 rounded-lg p-4 mb-4">
      <h2 className="text-sm font-semibold text-slate-800 mb-3">Form</h2>

      <div className="grid grid-cols-3 gap-2 pb-3 border-b border-slate-100">
        <StatTile label="Last 10" rate={form.win_rate_last_10} matches={form.matches_last_10} />
        <StatTile label="Last 20" rate={form.win_rate_last_20} matches={form.matches_last_20} />
        <StatTile label="Last 30" rate={form.win_rate_last_30} matches={form.matches_last_30} />
      </div>

      <div className="grid grid-cols-3 gap-2 py-3 border-b border-slate-100">
        <StatTile label="3 months" rate={form.win_rate_3m} matches={form.matches_3m} />
        <StatTile label="6 months" rate={form.win_rate_6m} matches={form.matches_6m} />
        <StatTile label="12 months" rate={form.win_rate_12m} matches={form.matches_12m} />
      </div>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-1 py-3 border-b border-slate-100 text-sm">
        {form.streak_type && (
          <span>
            Current streak:{' '}
            <span className={`font-semibold ${form.streak_type === 'W' ? 'text-green-700' : 'text-red-700'}`}>
              {form.streak_count}
              {form.streak_type}
            </span>
          </span>
        )}
        <span className="text-slate-500">
          {form.days_since_last_match !== null
            ? `Last match ${form.days_since_last_match} day${form.days_since_last_match === 1 ? '' : 's'} ago`
            : 'No recent match'}
        </span>
        <span className="text-slate-500">{form.matches_last_30_days} match(es) in the last 30 days</span>
      </div>

      {form.by_surface.length > 0 && (
        <div className="pt-3 space-y-1.5">
          {form.by_surface
            .slice()
            .sort((a, b) => b.matches - a.matches)
            .map((s) => (
              <div key={s.surface} className="flex items-center gap-2 text-sm">
                <span className="w-28 text-slate-600 truncate">{s.surface}</span>
                <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-500 rounded-full"
                    style={{ width: `${((s.win_rate ?? 0) * 100).toFixed(0)}%` }}
                  />
                </div>
                <span className="w-10 text-right tabular-nums text-slate-500">{pct(s.win_rate)}</span>
                <span className="w-16 text-right text-xs text-slate-400">
                  ({s.wins}/{s.matches})
                </span>
              </div>
            ))}
        </div>
      )}
    </div>
  )
}
