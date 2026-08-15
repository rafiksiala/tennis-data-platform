import { useParams, useNavigate, Link } from 'react-router-dom'
import { useMatch } from '../api/hooks'
import { StatusBadge } from '../components/StatusBadge'
import { countryFlag } from '../lib/countries'

const STAT_LABELS: Record<string, string> = {
  aces: 'Aces',
  double_faults: 'Double faults',
  first_serve_pct: '1st serve (%)',
  first_serve_points_won_pct: '1st serve points won (%)',
  second_serve_points_won_pct: '2nd serve points won (%)',
  break_points_saved_pct: 'Break points saved (%)',
  first_return_points_won_pct: '1st serve return points won (%)',
  second_return_points_won_pct: '2nd serve return points won (%)',
  break_points_converted_pct: 'Break points converted (%)',
  winners: 'Winners',
  unforced_errors: 'Unforced errors',
  net_points_won_pct: 'Net points won (%)',
  service_points_won_pct: 'Service points won (%)',
  return_points_won_pct: 'Return points won (%)',
  total_points_won: 'Total points won',
}

export function MatchDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { data: match, isLoading, isError } = useMatch(id ? Number(id) : undefined)

  if (isLoading) return <div className="max-w-2xl mx-auto px-4 py-6 text-slate-500 text-sm">Loading…</div>
  if (isError || !match)
    return <div className="max-w-2xl mx-auto px-4 py-6 text-red-600 text-sm">Match not found.</div>

  const matchStats = match.statistics.filter((s) => s.stat_period === 'match')
  const p1Stats = new Map(matchStats.filter((s) => s.player_id === match.player1?.id).map((s) => [s.stat_name, s]))
  const p2Stats = new Map(matchStats.filter((s) => s.player_id === match.player2?.id).map((s) => [s.stat_name, s]))
  const statNames = [...new Set(matchStats.map((s) => s.stat_name))]

  const latestOddsCapturedAt = match.odds.length > 0 ? match.odds[0].captured_at : null
  const latestOdds = match.odds.filter((o) => o.captured_at === latestOddsCapturedAt)

  return (
    <div className="max-w-2xl mx-auto px-4 py-6">
      <button onClick={() => navigate(-1)} className="text-sm text-blue-700 hover:underline mb-4">
        ← Back
      </button>

      <div className="bg-white border border-slate-200 rounded-lg p-4 mb-4">
        <div className="flex items-center justify-between mb-3">
          <div className="text-sm text-slate-500">
            {match.tournament.name}
            {match.tournament.surface && ` · ${match.tournament.surface}`}
            {match.round_code && ` · ${match.round_code}`}
          </div>
          <StatusBadge status={match.status} />
        </div>

        <div className="space-y-2">
          {[match.player1, match.player2].map((p, i) => (
            <div key={p?.id ?? i} className="flex items-center justify-between">
              {p ? (
                <Link
                  to={`/players/${p.id}`}
                  className={`hover:underline ${match.winner_id === p.id ? 'font-semibold text-slate-900' : 'text-slate-700'}`}
                >
                  {countryFlag(p.country_code)} {p.full_name}
                </Link>
              ) : (
                <span className="text-slate-400">TBD</span>
              )}
              {i === 0 && <span className="text-sm text-slate-500 tabular-nums">{match.score_raw}</span>}
            </div>
          ))}
        </div>

        {match.sets.length > 0 && (
          <table className="w-full mt-3 text-sm">
            <tbody>
              {[match.player1, match.player2].map((p, pi) => (
                <tr key={p?.id ?? pi}>
                  <td className="text-slate-600 py-0.5">{p?.full_name ?? 'TBD'}</td>
                  {match.sets.map((s) => (
                    <td key={s.set_number} className="text-center tabular-nums py-0.5 w-8">
                      {pi === 0 ? s.player1_games : s.player2_games}
                      {pi === 0 && s.tiebreak_player1_points !== null && (
                        <sup className="text-[10px] text-slate-400">{s.tiebreak_player1_points}</sup>
                      )}
                      {pi === 1 && s.tiebreak_player2_points !== null && (
                        <sup className="text-[10px] text-slate-400">{s.tiebreak_player2_points}</sup>
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {statNames.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-lg p-4 mb-4">
          <h2 className="text-sm font-semibold text-slate-800 mb-3">Match statistics</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-500 text-xs">
                <th className="text-left font-normal pb-2">{match.player1?.full_name}</th>
                <th className="font-normal pb-2"></th>
                <th className="text-right font-normal pb-2">{match.player2?.full_name}</th>
              </tr>
            </thead>
            <tbody>
              {statNames.map((name) => (
                <tr key={name} className="border-t border-slate-100">
                  <td className="py-1.5 tabular-nums">{p1Stats.get(name)?.stat_value ?? '-'}</td>
                  <td className="py-1.5 text-center text-xs text-slate-400">{STAT_LABELS[name] ?? name}</td>
                  <td className="py-1.5 text-right tabular-nums">{p2Stats.get(name)?.stat_value ?? '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {latestOdds.length > 0 && (
        <div className="bg-white border border-slate-200 rounded-lg p-4">
          <h2 className="text-sm font-semibold text-slate-800 mb-1">
            Match winner odds
            {match.odds[0].is_retroactive && (
              <span className="ml-2 text-[11px] font-normal text-amber-600">
                (captured retroactively, not necessarily the exact opening odds)
              </span>
            )}
          </h2>
          <table className="w-full text-sm mt-2">
            <thead>
              <tr className="text-slate-500 text-xs">
                <th className="text-left font-normal pb-1">Bookmaker</th>
                <th className="text-right font-normal pb-1">{match.player1?.full_name}</th>
                <th className="text-right font-normal pb-1">{match.player2?.full_name}</th>
              </tr>
            </thead>
            <tbody>
              {[...new Set(latestOdds.filter((o) => o.market === 'Home/Away').map((o) => o.bookmaker))].map(
                (bookmaker) => {
                  const home = latestOdds.find((o) => o.bookmaker === bookmaker && o.selection === 'Home')
                  const away = latestOdds.find((o) => o.bookmaker === bookmaker && o.selection === 'Away')
                  return (
                    <tr key={bookmaker} className="border-t border-slate-100">
                      <td className="py-1 text-slate-600">{bookmaker}</td>
                      <td className="py-1 text-right tabular-nums">{home?.odd_value ?? '-'}</td>
                      <td className="py-1 text-right tabular-nums">{away?.odd_value ?? '-'}</td>
                    </tr>
                  )
                },
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
