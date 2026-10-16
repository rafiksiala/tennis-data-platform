// Un jour du calendrier est une date du fuseau du visiteur, au format YYYY-MM-DD.
// L'API stocke et repond en UTC; c'est l'app qui convertit dans le fuseau du visiteur,
// pour l'affichage comme pour le decoupage en jours (ADR-0003).

// Date locale (fuseau du navigateur) de l'instant d. Surtout pas toISOString(), qui
// donne la date UTC: a New York apres 20h, ce serait deja le lendemain.
export function toDateStr(d: Date): string {
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${month}-${day}`
}

// Arithmetique de calendrier pure: faite en UTC, elle ne depend ni du fuseau ni des
// changements d'heure.
export function addDays(dateStr: string, days: number): string {
  const d = new Date(dateStr + 'T00:00:00Z')
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

// Intervalle [from, to[ du jour local dateStr, en instants UTC ISO (parametres from/to
// de /matches): de minuit local a minuit local du lendemain. Le jour dure donc 23 h ou
// 25 h aux changements d'heure. Si minuit n'existe pas localement (fuseaux qui changent
// d'heure a minuit, ex: America/Santiago), new Date(y, m, d) donne le premier instant du jour.
export function localDayBounds(dateStr: string): { from: string; to: string } {
  const [year, month, day] = dateStr.split('-').map(Number)
  return {
    from: new Date(year, month - 1, day).toISOString(),
    to: new Date(year, month - 1, day + 1).toISOString(),
  }
}

export function formatDateLabel(dateStr: string): string {
  const today = toDateStr(new Date())
  const yesterday = addDays(today, -1)
  const tomorrow = addDays(today, 1)
  if (dateStr === today) return 'Today'
  if (dateStr === yesterday) return 'Yesterday'
  if (dateStr === tomorrow) return 'Tomorrow'
  // dateStr est une date de calendrier, pas un instant: on la formate telle quelle (en UTC),
  // sinon un visiteur a l'ouest de Greenwich verrait la veille.
  return new Date(dateStr + 'T00:00:00Z').toLocaleDateString('en-US', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
  })
}

export function formatTime(isoStr: string | null): string {
  if (!isoStr) return '-'
  return new Date(isoStr).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
}
