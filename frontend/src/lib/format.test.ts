// Mirrors backend/tests/unit/test_money.py and test_timeutil.py so the UI shows the same values.
import { describe, expect, it } from 'vitest'
import { formatInr, formatIst, formatIstDate, istInputToIso, istInputToMs, msToIstInput, parseIstInput } from './format'

describe('formatInr', () => {
  it.each([
    [2500000, '₹25,000'],
    [1500000, '₹15,000'],
    [12500000, '₹1,25,000'],
    [1234567800, '₹1,23,45,678'],
    [1550, '₹15.50'],
    [99, '₹0.99'],
    [0, '₹0'],
  ])('%i paise -> %s', (paise, text) => {
    expect(formatInr(paise)).toBe(text)
  })

  it('shows a dash for a missing fee instead of zero', () => {
    expect(formatInr(null)).toBe('—')
  })
})

describe('IST display', () => {
  it('matches the backend demo clock display', () => {
    expect(formatIst(1792065600000)).toBe('15 Oct 2026, 17:30 IST')
  })

  it('shows seconds only when they are not zero', () => {
    expect(formatIst(Date.parse('2026-10-19T23:59:59+05:30'))).toBe('19 Oct 2026, 23:59:59 IST')
  })

  it('reads datetime-local input as IST', () => {
    expect(istInputToIso('2026-10-19T23:59')).toBe('2026-10-19T23:59:00+05:30')
    expect(istInputToMs('2026-10-20T09:00:00')).toBe(Date.parse('2026-10-20T03:30:00Z'))
  })

  it('round-trips through the input format', () => {
    const ms = Date.parse('2026-10-19T23:59:59+05:30')
    expect(istInputToMs(msToIstInput(ms))).toBe(ms)
  })
})

describe('incomplete date input (Review fix C4)', () => {
  it('treats an empty or partial datetime-local value as missing, not NaN', () => {
    expect(parseIstInput('')).toBeNull()
    expect(parseIstInput('2026-10-19')).toBeNull()
    expect(parseIstInput('2026-10-19T23:59:59+05:30')).toBeNull()
    expect(parseIstInput('2026-10-19T23:59')).toBe(Date.parse('2026-10-19T23:59:00+05:30'))
    expect(parseIstInput('2026-10-19T23:59:59')).toBe(Date.parse('2026-10-19T23:59:59+05:30'))
  })

  it('never throws when asked to display an invalid time', () => {
    expect(formatIst(Number.NaN)).toBe('—')
    expect(formatIstDate(Number.NaN)).toBe('—')
    expect(formatIst(istInputToMs(''))).toBe('—')
  })
})
