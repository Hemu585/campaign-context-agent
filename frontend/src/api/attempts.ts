// Idempotency bookkeeping for one kind of user action (API_CONTRACTS "Mutation headers").
//
// The server writes a receipt only together with the change, keyed by Idempotency-Key and a hash of
// the payload. So after a network error or a 5xx the earlier request may have been applied: the next
// attempt must resend the SAME payload under the SAME key, and the server then replays it instead of
// writing twice. Only an answer that proves nothing was written lets the action start fresh.
import { ApiError } from './client'

export type Outcome = 'success' | 'rejected' | 'uncertain' | 'conflict'

export function classify(err: unknown): Outcome {
  if (!(err instanceof ApiError) || err.status === 0 || err.status >= 500) return 'uncertain'
  // The key was already used with another payload: the earlier attempt may have landed. Keep the
  // key so nothing new is written under a fresh one; the operator reloads to see the saved state.
  if (err.code === 'IDEMPOTENCY_CONFLICT') return 'conflict'
  return 'rejected'
}

export class WriteAttempts<T> {
  private key: string
  private held: T | null = null

  constructor(private readonly newKey: () => string) {
    this.key = newKey()
  }

  /** What to send now: an unresolved earlier payload goes again, unchanged, under its key. */
  begin(args: T): { key: string; payload: T; replaying: boolean } {
    if (this.held !== null) return { key: this.key, payload: this.held, replaying: true }
    this.held = args
    return { key: this.key, payload: args, replaying: false }
  }

  settle(outcome: Outcome): void {
    if (outcome === 'success' || outcome === 'rejected') {
      this.held = null
      this.key = this.newKey()
    }
    // 'uncertain' and 'conflict' keep both the key and the payload.
  }
}
