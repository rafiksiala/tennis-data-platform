import { useNavigate, Link } from 'react-router-dom'
import type { MatchOut, PlayerOut } from '../api/types'
import { formatTime } from '../lib/date'
import { countryFlag } from '../lib/countries'
import { StatusBadge } from './StatusBadge'

function PlayerLine({
  player,
  isWinner,
  hasWinner,
}: {
  player: PlayerOut | null
  isWinner: boolean
  hasWinner: boolean
}) {
  if (!player) return <span className="text-slate-400">TBD</span>
  return (
    <Link
      to={`/players/${player.id}`}
      onClick={(e) => e.stopPropagation()}
      className={`hover:underline ${hasWinner && isWinner ? 'font-semibold text-slate-900' : 'text-slate-700'}`}
    >
      {countryFlag(player.country_code)} {player.full_name}
    </Link>
  )
}

export function MatchRow({ match }: { match: MatchOut }) {
  const navigate = useNavigate()
  const hasWinner = match.winner_id !== null

  return (
    <div
      onClick={() => navigate(`/matches/${match.id}`)}
      className="grid grid-cols-[56px_1fr_auto_90px] items-center gap-3 px-3 py-2 hover:bg-slate-50 cursor-pointer border-b border-slate-100 last:border-0"
    >
      <div className="text-xs text-slate-500 tabular-nums">
        {match.status === 'scheduled' ? formatTime(match.scheduled_at) : (match.round_code ?? '')}
      </div>

      <div className="min-w-0 flex flex-col gap-0.5 text-sm">
        <PlayerLine player={match.player1} isWinner={match.winner_id === match.player1?.id} hasWinner={hasWinner} />
        <PlayerLine player={match.player2} isWinner={match.winner_id === match.player2?.id} hasWinner={hasWinner} />
      </div>

      <div className="text-sm text-slate-600 tabular-nums whitespace-nowrap">{match.score_raw ?? ''}</div>

      <div className="flex justify-end">
        <StatusBadge status={match.status} />
      </div>
    </div>
  )
}
