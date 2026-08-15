import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { usePlayerSearch } from '../api/hooks'
import { countryFlag } from '../lib/countries'

export function PlayerSearch() {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const { data: results } = usePlayerSearch(q)

  return (
    <div className="relative w-56">
      <input
        type="text"
        value={q}
        onChange={(e) => {
          setQ(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder="Search a player…"
        className="w-full border border-slate-200 rounded-lg px-2 py-1.5 text-sm bg-white text-slate-700"
      />
      {open && results && results.length > 0 && (
        <div className="absolute z-10 mt-1 w-full bg-white border border-slate-200 rounded-lg shadow-sm max-h-64 overflow-y-auto">
          {results.map((p) => (
            <div
              key={p.id}
              onClick={() => {
                navigate(`/players/${p.id}`)
                setQ('')
                setOpen(false)
              }}
              className="px-3 py-2 text-sm hover:bg-slate-50 cursor-pointer"
            >
              {countryFlag(p.country_code)} {p.full_name}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
