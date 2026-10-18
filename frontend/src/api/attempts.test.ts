// Review fix C1: a write whose response was lost must not turn into a second write.
import { describe, expect, it } from 'vitest'
import { WriteAttempts, classify } from './attempts'
import { ApiError } from './client'

function counterKeys() {
  let n = 0
  return () => `key-${++n}`
}

describe('WriteAttempts', () => {
  it('starts a fresh action with a new key after success', () => {
    const a = new WriteAttempts<{ revision: number }>(counterKeys())
    expect(a.begin({ revision: 1 })).toEqual({ key: 'key-1', payload: { revision: 1 }, replaying: false })
    a.settle('success')
    expect(a.begin({ revision: 2 })).toEqual({ key: 'key-2', payload: { revision: 2 }, replaying: false })
  })

  it('resends the original payload under the same key while the outcome is unknown', () => {
    const a = new WriteAttempts<{ revision: number }>(counterKeys())
    a.begin({ revision: 1 })
    a.settle('uncertain')
    // The form meanwhile shows revision 2 (the lost request DID land), but the retry must replay
    // the original request so the server answers from its receipt instead of writing again.
    expect(a.begin({ revision: 2 })).toEqual({ key: 'key-1', payload: { revision: 1 }, replaying: true })
  })

  it('starts fresh only after an answer proving nothing was written', () => {
    const a = new WriteAttempts<{ revision: number }>(counterKeys())
    a.begin({ revision: 1 })
    a.settle('uncertain')
    a.begin({ revision: 2 })
    a.settle('rejected') // e.g. 409 STALE_CONTEXT for the replayed payload: nothing was written
    expect(a.begin({ revision: 3 })).toEqual({ key: 'key-2', payload: { revision: 3 }, replaying: false })
  })

  it('never renews the key after an idempotency conflict', () => {
    const a = new WriteAttempts<{ revision: number }>(counterKeys())
    a.begin({ revision: 1 })
    a.settle('conflict')
    expect(a.begin({ revision: 5 })).toEqual({ key: 'key-1', payload: { revision: 1 }, replaying: true })
  })
})

describe('classify', () => {
  it('treats lost responses and server errors as possibly applied', () => {
    expect(classify(new ApiError(0, 'BACKEND_UNREACHABLE', 'down', true))).toBe('uncertain')
    expect(classify(new ApiError(500, 'INTERNAL_ERROR', 'boom'))).toBe('uncertain')
    expect(classify(new TypeError('unexpected'))).toBe('uncertain')
  })

  it('treats refusals as nothing written, except an idempotency conflict', () => {
    expect(classify(new ApiError(409, 'STALE_CONTEXT', 'changed'))).toBe('rejected')
    expect(classify(new ApiError(422, 'INVALID_INPUT', 'bad'))).toBe('rejected')
    expect(classify(new ApiError(409, 'IDEMPOTENCY_CONFLICT', 'used'))).toBe('conflict')
  })
})
