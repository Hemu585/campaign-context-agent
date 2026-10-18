// Minimal fetch client for the local API. Writes carry JSON, the per-process nonce from
// /api/bootstrap and an Idempotency-Key; the server enforces all of it (API_CONTRACTS).
import type { Bootstrap, ErrorEnvelope } from './types'

export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? 'http://127.0.0.1:8000'

export class ApiError extends Error {
  status: number
  code: string
  retryable: boolean
  details: Record<string, unknown>

  constructor(status: number, code: string, message: string, retryable = false, details: Record<string, unknown> = {}) {
    super(message)
    this.status = status
    this.code = code
    this.retryable = retryable
    this.details = details
  }
}

let nonce: string | null = null

export function rememberNonce(value: string): void {
  nonce = value
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(API_BASE + path, init)
  } catch {
    throw new ApiError(0, 'BACKEND_UNREACHABLE', `The local backend is not answering at ${API_BASE}. Start it with uvicorn, then retry.`, true)
  }
}

async function decode<T>(res: Response, { allow503 = false } = {}): Promise<T> {
  const text = await res.text()
  let body: unknown = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    throw new ApiError(res.status, 'INVALID_RESPONSE', 'The backend sent a response that is not JSON.')
  }
  if (res.ok || (allow503 && res.status === 503)) return body as T
  const err = (body as ErrorEnvelope | null)?.error
  throw new ApiError(res.status, err?.code ?? `HTTP_${res.status}`, err?.message ?? res.statusText, err?.retryable ?? false,
    (err?.details as Record<string, unknown> | undefined) ?? {})
}

export async function getJson<T>(path: string, opts: { allow503?: boolean } = {}): Promise<T> {
  return decode<T>(await request(path, { headers: { Accept: 'application/json' } }), opts)
}

export async function loadBootstrap(): Promise<Bootstrap> {
  const boot = await getJson<Bootstrap>('/api/bootstrap')
  rememberNonce(boot.nonce)
  return boot
}

export async function sendJson<T>(method: 'POST' | 'PATCH', path: string, body: unknown, idempotencyKey: string): Promise<T> {
  if (!nonce) await loadBootstrap()
  const send = () => request(path, {
    method,
    headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-Local-Nonce': nonce ?? '', 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify(body),
  })
  try {
    return await decode<T>(await send())
  } catch (err) {
    // The backend restarted (new nonce): refresh it once and retry with the SAME key, which is safe
    // because the server deduplicates by Idempotency-Key.
    if (err instanceof ApiError && err.code === 'INVALID_NONCE') {
      await loadBootstrap()
      return decode<T>(await send())
    }
    throw err
  }
}

export function newKey(): string {
  return crypto.randomUUID()
}
