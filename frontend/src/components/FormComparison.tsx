import type { PlayerFormOut } from '../api/types'

function pct(rate: number | null | undefined): string {
  return rate === null || rate === undefined ? '-' : `${Math.round(rate * 100)}%`
}

function streakLabel(form: PlayerFormOut | undefined): string {
  if (!form?.streak_type) return '-'
  return `${form.streak_count}${form.streak_type}`
}

function surfaceWinRate(form: PlayerFormOut | undefined, surface: string | null): number | null {
  if (!form || !surface) return null
  return form.by_surface.find((s) => s.surface === surface)?.win_rate ?? null
}

export function FormComparison({
  player1Form,
  player2Form,
  surface,
}: {
  player1Form: PlayerFormOut | undefined
  player2Form: PlayerFormOut | undefined
  surface: string | null
}) {
  if (!player1Form && !player2Form) return null

  const rows: { label: string; p1: string; p2: string }[] = [
    { label: 'Last 10 matches', p1: pct(player1Form?.win_rate_last_10), p2: pct(player2Form?.win_rate_last_10) },
    { label: 'Last 20 matches', p1: pct(player1Form?.win_rate_last_20), p2: pct(player2Form?.win_rate_last_20) },
    { label: 'Last 30 matches', p1: pct(player1Form?.win_rate_last_30), p2: pct(player2Form?.win_rate_last_30) },
    { label: 'Last 3 months', p1: pct(player1Form?.win_rate_3m), p2: pct(player2Form?.win_rate_3m) },
    { label: 'Last 6 months', p1: pct(player1Form?.win_rate_6m), p2: pct(player2Form?.win_rate_6m) },
    { label: 'Last 12 months', p1: pct(player1Form?.win_rate_12m), p2: pct(player2Form?.win_rate_12m) },
    ...(surface
      ? [
          {
            label: `On ${surface}`,
            p1: pct(surfaceWinRate(player1Form, surface)),
            p2: pct(surfaceWinRate(player2Form, surface)),
          },
        ]
      : []),
    { label: 'Current streak', p1: streakLabel(player1Form), p2: streakLabel(player2Form) },
    {
      label: 'Days since last match',
      p1: player1Form?.days_since_last_match?.toString() ?? '-',
      p2: player2Form?.days_since_last_match?.toString() ?? '-',
    },
  ]

  return (
    <div className="bg-white border border-slate-200 rounded-lg p-4 mb-4">
      <h2 className="text-sm font-semibold text-slate-800 mb-3">Form comparison</h2>
      <table className="w-full text-sm">
        <tbody>
          {rows.map((row) => (
            <tr key={row.label} className="border-t border-slate-100 first:border-0">
              <td className="py-1.5 w-16 tabular-nums font-medium text-slate-800">{row.p1}</td>
              <td className="py-1.5 text-center text-xs text-slate-400">{row.label}</td>
              <td className="py-1.5 w-16 text-right tabular-nums font-medium text-slate-800">{row.p2}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
