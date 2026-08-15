import { addDays, formatDateLabel } from '../lib/date'

interface Props {
  date: string
  onDateChange: (date: string) => void
  tour: string
  onTourChange: (tour: string) => void
  status: string
  onStatusChange: (status: string) => void
}

const TOURS = [
  { value: '', label: 'Tous les tours' },
  { value: 'atp', label: 'ATP' },
  { value: 'wta', label: 'WTA' },
  { value: 'challenger_men', label: 'Challenger H' },
  { value: 'challenger_women', label: 'Challenger F' },
]

const STATUSES = [
  { value: '', label: 'Tous les statuts' },
  { value: 'live', label: 'En direct' },
  { value: 'scheduled', label: 'À venir' },
  { value: 'finished', label: 'Terminés' },
]

export function FilterBar({ date, onDateChange, tour, onTourChange, status, onStatusChange }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-2 mb-4">
      <div className="flex items-center gap-1 bg-white border border-slate-200 rounded-lg px-1">
        <button
          onClick={() => onDateChange(addDays(date, -1))}
          className="px-2 py-1.5 text-slate-500 hover:text-slate-900"
          aria-label="Jour precedent"
        >
          ←
        </button>
        <span className="px-2 text-sm font-medium text-slate-800 min-w-[110px] text-center">
          {formatDateLabel(date)}
        </span>
        <button
          onClick={() => onDateChange(addDays(date, 1))}
          className="px-2 py-1.5 text-slate-500 hover:text-slate-900"
          aria-label="Jour suivant"
        >
          →
        </button>
      </div>

      <select
        value={tour}
        onChange={(e) => onTourChange(e.target.value)}
        className="border border-slate-200 rounded-lg px-2 py-1.5 text-sm bg-white text-slate-700"
      >
        {TOURS.map((t) => (
          <option key={t.value} value={t.value}>
            {t.label}
          </option>
        ))}
      </select>

      <select
        value={status}
        onChange={(e) => onStatusChange(e.target.value)}
        className="border border-slate-200 rounded-lg px-2 py-1.5 text-sm bg-white text-slate-700"
      >
        {STATUSES.map((s) => (
          <option key={s.value} value={s.value}>
            {s.label}
          </option>
        ))}
      </select>
    </div>
  )
}
