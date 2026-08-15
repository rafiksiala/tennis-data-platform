export function toDateStr(d: Date): string {
  return d.toISOString().slice(0, 10)
}

export function addDays(dateStr: string, days: number): string {
  const d = new Date(dateStr + 'T00:00:00Z')
  d.setUTCDate(d.getUTCDate() + days)
  return toDateStr(d)
}

export function formatDateLabel(dateStr: string): string {
  const today = toDateStr(new Date())
  const yesterday = addDays(today, -1)
  const tomorrow = addDays(today, 1)
  if (dateStr === today) return "Aujourd'hui"
  if (dateStr === yesterday) return 'Hier'
  if (dateStr === tomorrow) return 'Demain'
  return new Date(dateStr + 'T00:00:00Z').toLocaleDateString('fr-FR', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  })
}

export function formatTime(isoStr: string | null): string {
  if (!isoStr) return '-'
  return new Date(isoStr).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
}
