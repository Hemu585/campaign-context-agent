// Display formatting that mirrors the backend (app/money.py, app/timeutil.py). Values are stored as
// integer paise and UTC milliseconds; strings exist only for display.

function groupIndian(rupees: number): string {
  const digits = String(rupees)
  if (digits.length <= 3) return digits
  let head = digits.slice(0, -3)
  const tail = digits.slice(-3)
  const groups: string[] = []
  while (head.length > 2) {
    groups.unshift(head.slice(-2))
    head = head.slice(0, -2)
  }
  if (head) groups.unshift(head)
  return [...groups, tail].join(',')
}

export function formatInr(paise: number | null | undefined): string {
  if (paise === null || paise === undefined) return '—'
  const rupees = Math.floor(paise / 100)
  const rem = paise % 100
  return `₹${groupIndian(rupees)}${rem ? '.' + String(rem).padStart(2, '0') : ''}`
}

const IST_PARTS = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Kolkata', day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  second: '2-digit', hourCycle: 'h23',
})

function istParts(ms: number): Record<string, string> {
  return Object.fromEntries(IST_PARTS.formatToParts(new Date(ms)).map((p) => [p.type, p.value]))
}

export function formatIst(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return '—'
  const p = istParts(ms)
  const clock = p.second && p.second !== '00' ? `${p.hour}:${p.minute}:${p.second}` : `${p.hour}:${p.minute}`
  return `${p.day} ${p.month} ${p.year}, ${clock} IST`
}

export function formatIstDate(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return '—'
  const p = istParts(ms)
  return `${p.day} ${p.month} ${p.year}`
}

/** A datetime-local value ("2026-10-19T23:59" or with seconds) read as Indian Standard Time. */
export function istInputToIso(value: string): string {
  const withSeconds = value.length === 16 ? `${value}:00` : value
  return `${withSeconds}+05:30`
}

export function istInputToMs(value: string): number {
  return Date.parse(istInputToIso(value))
}

/** An IST datetime-local value as UTC milliseconds, or null when it is empty or incomplete. */
export function parseIstInput(value: string): number | null {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$/.test(value)) return null
  const ms = istInputToMs(value)
  return Number.isFinite(ms) ? ms : null
}

/** UTC milliseconds to a datetime-local value in IST, with seconds. */
export function msToIstInput(ms: number): string {
  const shifted = new Date(ms + 5.5 * 3_600_000)
  return shifted.toISOString().slice(0, 19)
}

export function elapsed(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—'
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`
}

export function initials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join('')
}
