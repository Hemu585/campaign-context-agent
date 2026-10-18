import { useEffect, useRef, useState } from 'react'
import type { Run, SessionDetail } from '../api/types'
import { ApiError } from '../api/client'
import { elapsed } from '../lib/format'
import { PHASE_LABEL, RUN_STATUS_LABEL, TOOL_LABEL, reasonLabel } from '../lib/labels'
import { Banner } from './ui'

export const SUGGESTED_PROMPT = 'Find a replacement for this campaign and explain any conflicts.'
const ACTIVE = new Set(['queued', 'running'])

function useTicker(active: boolean) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [active])
  return now
}

function RunProgress({ run }: { run: Run }) {
  const active = ACTIVE.has(run.status) && run.active
  const now = useTicker(active)
  const tools = (run.trace ?? []).filter((t) => t.type === 'tool')
  const since = run.started_at_ms ?? run.created_at_ms
  return (
    <div className="progress" aria-label="Agent progress">
      <div className="progress-head">
        <strong>Agent run</strong>
        <span className="mono">{run.id}</span>
        <span className="model" title={run.model_digest ? `${run.model} · digest ${run.model_digest.slice(0, 12)}` : undefined}>{run.model}</span>
      </div>
      <ol>
        {tools.map((t) => (
          <li key={t.seq}>
            <span aria-hidden="true" style={{ color: t.status === 'ok' ? 'var(--ok)' : 'var(--bad)', fontWeight: 700 }}>{t.status === 'ok' ? '✓' : '✕'}</span>
            <span>
              {TOOL_LABEL[t.tool ?? ''] ?? t.tool}
              {t.args && typeof t.args.creator_id === 'string' ? <> · <span className="mono">{t.args.creator_id}</span></> : null}
              {t.status !== 'ok' ? <> · refused: {reasonLabel(t.error_code) || t.error_code}</> : null}
            </span>
            <span className="t">{elapsed(t.elapsed_ms)}</span>
          </li>
        ))}
        {active ? (
          <li className="live">
            <span className="pulse" aria-hidden="true" />
            <span>{PHASE_LABEL[run.phase ?? 'queued'] ?? run.phase}: waiting for the local model</span>
            <span className="t">{Math.max(0, Math.round((now - since) / 1000))} s</span>
          </li>
        ) : null}
      </ol>
    </div>
  )
}

export function Conversation({ session, run, blocked, starting, cancelling, startError, onRun, onCancel }: {
  session: SessionDetail | undefined
  run: Run | undefined
  /** Why the agent cannot run right now (services checking or down), or null when it can. */
  blocked: string | null
  starting: boolean
  cancelling: boolean
  startError: unknown
  onRun: (message: string) => void
  onCancel: (runId: string) => void
}) {
  const [draft, setDraft] = useState(SUGGESTED_PROMPT)
  const listRef = useRef<HTMLDivElement>(null)
  const active = !!run && ACTIVE.has(run.status)
  const messages = session?.messages ?? []

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight })
  }, [messages.length, run?.status])

  const lastUserText = run ? messages.find((m) => m.run_id === run.id && m.role === 'user')?.text : undefined
  const failed = run && ['failed', 'cancelled', 'interrupted'].includes(run.status)
  // "Running" in the graph with no backend task behind it (see the runner's _end_safely).
  const orphaned = active && !run!.active
  const statusLine = run ? `${RUN_STATUS_LABEL[run.status]}${active ? ` · ${PHASE_LABEL[run.phase ?? 'queued'] ?? ''}` : ''}` : 'No run yet'

  return (
    <section className="card conversation" aria-labelledby="conv-title">
      <div className="card-head">
        <h2 id="conv-title">Agent conversation</h2>
        <span className="meta">{session ? `${session.title} · ${session.runs.length} run${session.runs.length === 1 ? '' : 's'}` : 'New session'}</span>
      </div>
      <div className="sr-only" aria-live="polite">{statusLine}</div>
      <div className="messages" ref={listRef}>
        {messages.length === 0 ? (
          <p className="empty-hint">Ask the local agent for a replacement. It reads the graph, checks every creator and can stage a draft proposal. Only you can approve it.</p>
        ) : messages.map((m) => (
          <div key={m.id} className={`msg ${m.role}`}>
            <div className="who">{m.role === 'user' ? 'You' : 'Agent · checked facts'}</div>
            <div className="bubble">{m.text}</div>
          </div>
        ))}
      </div>
      {run && (active || (run.trace?.length ?? 0) > 0) ? <RunProgress run={run} /> : null}
      {failed ? (
        <div style={{ padding: '0 16px 8px' }}>
          <Banner tone="error" title={`Run ${RUN_STATUS_LABEL[run!.status].toLowerCase()}.`}
            actions={lastUserText ? <button type="button" className="btn small" disabled={!!blocked || starting} onClick={() => onRun(lastUserText)}>Retry</button> : undefined}>
            {run!.error?.message} <span className="mono">({run!.error?.code})</span> Nothing was approved.
          </Banner>
        </div>
      ) : null}
      {orphaned ? (
        <div style={{ padding: '0 16px 8px' }}>
          <Banner tone="error" title="The backend is no longer working on this run.">
            Cancel it to record the stop, then run again. Nothing was approved.
          </Banner>
        </div>
      ) : null}
      {run?.status === 'needs_clarification' ? (
        <div style={{ padding: '0 16px 8px' }}><Banner tone="info" title="The agent needs a narrower request." /></div>
      ) : null}
      {startError ? (
        <div style={{ padding: '0 16px 8px' }}>
          <Banner tone="error" title="The run did not start.">
            {startError instanceof ApiError ? `${startError.message} (${startError.code})` : String(startError)}
          </Banner>
        </div>
      ) : null}
      <form className="composer" onSubmit={(e) => { e.preventDefault(); if (draft.trim()) onRun(draft.trim()) }}>
        <label htmlFor="prompt" className="sr-only">Request for the agent</label>
        <textarea id="prompt" value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={4000} rows={2} disabled={active} />
        <div className="composer-row">
          <span className="note">{blocked ?? 'Runs on the local model via Ollama. A warm run takes about 35 s.'}</span>
          {active ? (
            <button type="button" className="btn" onClick={() => onCancel(run!.id)} disabled={cancelling}>Cancel run</button>
          ) : null}
          <button type="submit" className="btn primary" disabled={active || starting || !!blocked || !draft.trim()}>
            {starting ? 'Starting…' : 'Run agent'}
          </button>
        </div>
      </form>
    </section>
  )
}
