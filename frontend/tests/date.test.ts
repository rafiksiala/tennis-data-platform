// Decoupage du calendrier en jours locaux (ADR-0003). Lancer: npm test (runner integre
// de Node, aucune dependance). Chaque fichier de test tourne dans son propre processus:
// changer TZ ici n'affecte que ce fichier.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { addDays, formatDateLabel, localDayBounds, toDateStr } from '../src/lib/date.ts'

// Node applique a la volee un changement de process.env.TZ (Date et Intl).
function inZone(timeZone: string, fn: () => void) {
  const previous = process.env.TZ
  process.env.TZ = timeZone
  try {
    assert.equal(Intl.DateTimeFormat().resolvedOptions().timeZone, timeZone)
    fn()
  } finally {
    if (previous === undefined) delete process.env.TZ
    else process.env.TZ = previous
  }
}

// Valeurs attendues calculees independamment avec zoneinfo (Python, tzdata 2026e).
const CASES: { zone: string; day: string; from: string; to: string; note: string }[] = [
  { zone: 'America/New_York', day: '2026-07-01', from: '2026-07-01T04:00:00.000Z', to: '2026-07-02T04:00:00.000Z', note: '24 h' },
  { zone: 'America/New_York', day: '2026-03-08', from: '2026-03-08T05:00:00.000Z', to: '2026-03-09T04:00:00.000Z', note: '23 h, heure d ete' },
  { zone: 'America/New_York', day: '2026-11-01', from: '2026-11-01T04:00:00.000Z', to: '2026-11-02T05:00:00.000Z', note: '25 h, heure d hiver' },
  { zone: 'Europe/Paris', day: '2026-03-29', from: '2026-03-28T23:00:00.000Z', to: '2026-03-29T22:00:00.000Z', note: '23 h' },
  { zone: 'Europe/Paris', day: '2026-10-25', from: '2026-10-24T22:00:00.000Z', to: '2026-10-25T23:00:00.000Z', note: '25 h' },
  { zone: 'Australia/Sydney', day: '2026-04-05', from: '2026-04-04T13:00:00.000Z', to: '2026-04-05T14:00:00.000Z', note: '25 h, hemisphere sud' },
  { zone: 'Australia/Sydney', day: '2026-10-04', from: '2026-10-03T14:00:00.000Z', to: '2026-10-04T13:00:00.000Z', note: '23 h, hemisphere sud' },
  { zone: 'Asia/Tokyo', day: '2026-07-01', from: '2026-06-30T15:00:00.000Z', to: '2026-07-01T15:00:00.000Z', note: 'commence la veille en UTC' },
  // minuit n'existe pas (00:00 -> 01:00): le jour commence a 01:00 locale
  { zone: 'America/Santiago', day: '2023-09-03', from: '2023-09-03T04:00:00.000Z', to: '2023-09-04T03:00:00.000Z', note: 'minuit saute' },
  // minuit existe deux fois (01:00 -> 00:00): le jour commence au premier
  { zone: 'America/Havana', day: '2023-11-05', from: '2023-11-05T04:00:00.000Z', to: '2023-11-06T05:00:00.000Z', note: 'minuit double' },
]

for (const { zone, day, from, to, note } of CASES) {
  test(`localDayBounds ${day} a ${zone} (${note})`, () => {
    inZone(zone, () => assert.deepEqual(localDayBounds(day), { from, to }))
  })
}

const ZONES = ['UTC', 'America/New_York', 'Europe/Paris', 'Australia/Sydney', 'America/Santiago', 'America/Havana']

test('les jours locaux se suivent sans trou ni chevauchement sur toute une annee', () => {
  for (const zone of ZONES) {
    inZone(zone, () => {
      for (let day = '2026-01-01'; day < '2027-01-01'; day = addDays(day, 1)) {
        const { from, to } = localDayBounds(day)
        const start = Date.parse(from)
        const end = Date.parse(to)
        assert.equal(to, localDayBounds(addDays(day, 1)).from, `${zone} ${day}`)
        assert.equal(toDateStr(new Date(start)), day, `${zone} ${day}: premier instant`)
        assert.notEqual(toDateStr(new Date(start - 1)), day, `${zone} ${day}: veille`)
        assert.equal(toDateStr(new Date(end - 1)), day, `${zone} ${day}: dernier instant`)
        const hours = (end - start) / 3_600_000
        assert.ok(hours >= 23 && hours <= 25, `${zone} ${day}: ${hours} h`)
      }
    })
  }
})

test('toDateStr donne la date locale, pas la date UTC', () => {
  inZone('America/New_York', () => assert.equal(toDateStr(new Date('2026-07-02T03:30:00Z')), '2026-07-01'))
  inZone('Asia/Tokyo', () => assert.equal(toDateStr(new Date('2026-06-30T16:00:00Z')), '2026-07-01'))
})

test('addDays est de l arithmetique de calendrier, quel que soit le fuseau', () => {
  for (const zone of ['America/New_York', 'Asia/Tokyo']) {
    inZone(zone, () => {
      assert.equal(addDays('2026-03-07', 1), '2026-03-08')
      assert.equal(addDays('2026-03-08', 1), '2026-03-09')
      assert.equal(addDays('2026-11-01', -1), '2026-10-31')
      assert.equal(addDays('2026-12-31', 1), '2027-01-01')
      assert.equal(addDays('2024-03-01', -1), '2024-02-29')
    })
  }
})

test('formatDateLabel affiche le jour demande, meme a l ouest de Greenwich', () => {
  inZone('America/New_York', () => {
    assert.match(formatDateLabel('2026-07-01'), /^Wed\W+Jul 1$/)
    assert.equal(formatDateLabel(toDateStr(new Date())), 'Today')
  })
})
