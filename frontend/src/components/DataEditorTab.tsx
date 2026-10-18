import { useState } from 'react'
import { ApiError } from '../api/client'
import { useEditFact } from '../api/hooks'
import type { EditableAgreement, EditableAvailability, EditableFacts, EditResult } from '../api/types'
import { formatIst, istInputToIso, msToIstInput, parseIstInput } from '../lib/format'
import { Banner } from './ui'

type Row = ({ kind: 'agreement' } & EditableAgreement) | ({ kind: 'availability' } & EditableAvailability)

function Editor({ row, revision, campaignId, onDone, onCancel, onReload }: {
  row: Row; revision: number; campaignId: string; onDone: (r: EditResult) => void; onCancel: () => void; onReload: () => void
}) {
  // The edit is bound to the fact and revision shown when the editor opened. If anything changed
  // since, the operator reloads explicitly; a newer change is never silently overwritten.
  const [base] = useState(() => ({ row, revision }))
  const [start, setStart] = useState(base.row.start_ms ? msToIstInput(base.row.start_ms) : '')
  const [end, setEnd] = useState(base.row.end_ms ? msToIstInput(base.row.end_ms) : '')
  const [status, setStatus] = useState(base.row.status ?? '')
  const [exclusive, setExclusive] = useState(base.row.kind === 'agreement' ? !!base.row.exclusive : false)
  const [reason, setReason] = useState('')
  const edit = useEditFact(campaignId)
  const err = edit.error instanceof ApiError ? edit.error : null
  const stale = revision !== base.revision

  const startMs = parseIstInput(start)
  const endMs = parseIstInput(end)
  const problems: string[] = []
  if (base.row.start_ms !== null && startMs === null) problems.push('Enter a complete start date and time.')
  if (base.row.end_ms !== null && endMs === null) problems.push('Enter a complete end date and time.')
  if (startMs !== null && endMs !== null && endMs < startMs) problems.push('The end cannot be before the start.')

  const changes: Record<string, unknown> = {}
  if (startMs !== null && startMs !== base.row.start_ms) changes.start_at = istInputToIso(start)
  if (endMs !== null && endMs !== base.row.end_ms) changes.end_at = istInputToIso(end)
  if (status !== base.row.status) changes.status = status
  if (base.row.kind === 'agreement' && exclusive !== !!base.row.exclusive) changes.exclusive = exclusive
  const statuses = base.row.kind === 'agreement' ? ['active', 'cancelled'] : ['available', 'unavailable']
  const canSave = Object.keys(changes).length > 0 && problems.length === 0 && !!reason.trim() && !stale && !edit.isPending

  return (
    <form className="form-grid" style={{ padding: '10px 12px', background: 'var(--surface-sunk)', borderRadius: 8, marginTop: 8 }}
      onSubmit={(e) => {
        e.preventDefault()
        if (!canSave) return
        edit.mutate({ type: base.row.kind, id: base.row.id, changes, reason: reason.trim(), expected_revision: base.revision }, { onSuccess: onDone })
      }}>
      {stale || err?.code === 'STALE_CONTEXT' ? (
        <Banner tone="stale" title="This information changed after you opened the editor."
          actions={<button type="button" className="btn small" onClick={onReload}>Reload current values</button>}>
          Saving now could overwrite a newer change, so it is disabled until you reload.
        </Banner>
      ) : null}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <label>Start (IST)<input type="datetime-local" step={1} value={start} onChange={(e) => setStart(e.target.value)} /></label>
        <label>End (IST)<input type="datetime-local" step={1} value={end} onChange={(e) => setEnd(e.target.value)} /></label>
        <label>Status
          <select value={status} onChange={(e) => setStatus(e.target.value)}>{statuses.map((s) => <option key={s} value={s}>{s}</option>)}</select>
        </label>
        {base.row.kind === 'agreement' ? (
          <label className="radio" style={{ alignSelf: 'end' }}><input type="checkbox" checked={exclusive} onChange={(e) => setExclusive(e.target.checked)} /> Exclusive</label>
        ) : null}
      </div>
      {problems.map((p) => <p key={p} className="error-text" role="alert">{p}</p>)}
      {Object.keys(changes).length > 0 ? (
        <div className="diff" aria-label="Changes">
          {'start_at' in changes ? <><span>Start</span><span className="old">{formatIst(base.row.start_ms)}</span><span className="new">{formatIst(startMs)}</span></> : null}
          {'end_at' in changes ? <><span>End</span><span className="old">{formatIst(base.row.end_ms)}</span><span className="new">{formatIst(endMs)}</span></> : null}
          {'status' in changes ? <><span>Status</span><span className="old">{base.row.status}</span><span className="new">{status}</span></> : null}
          {'exclusive' in changes ? <><span>Exclusive</span><span className="old">{String(base.row.kind === 'agreement' && base.row.exclusive)}</span><span className="new">{String(exclusive)}</span></> : null}
        </div>
      ) : <p className="cell-note">Change a value to see old and new side by side.</p>}
      <label>Reason for the edit <span className="hint">Required; shown inside the new source version.</span>
        <input type="text" required maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      {err && err.code !== 'STALE_CONTEXT' ? <p className="error-text" role="alert">{err.message} ({err.code})</p> : null}
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button type="button" className="btn" onClick={onCancel}>Cancel</button>
        <button type="submit" className="btn primary" disabled={!canSave}>
          {edit.isPending ? 'Saving…' : 'Save new version'}
        </button>
      </div>
    </form>
  )
}

export function DataEditorTab({ facts, revision, campaignId, onSource, onRefresh }: {
  facts: EditableFacts | undefined; revision: number | undefined; campaignId: string; onSource: (id: string) => void
  /** Fetches the current facts; reloading an editor waits for it so it never reopens on a cached copy. */
  onRefresh: () => Promise<unknown>
}) {
  const [editing, setEditing] = useState<string | null>(null)
  const [opened, setOpened] = useState(0) // bumping it reopens the editor on the current values
  const [last, setLast] = useState<EditResult | null>(null)
  if (!facts) return <p className="cell-note">Loading editable facts…</p>
  if (!facts.demo_mode) return <Banner tone="info" title="Editing is off.">The backend is not in demo mode.</Banner>
  const rows: Row[] = [
    ...facts.agreements.map((a) => ({ kind: 'agreement' as const, ...a })),
    ...facts.availability.map((a) => ({ kind: 'availability' as const, ...a })),
  ]
  return (
    <div>
      <p className="scope-note">
        Fictional demo data only. Each edit writes a new source version attested by you; the old version stays readable
        and saved decisions keep their original evidence. Only agreement and availability fields can change.
      </p>
      {last ? (
        <Banner tone="stale" title="New source version saved.">
          <button type="button" className="btn link" onClick={() => onSource(last.source_id)}>{last.source_id}</button> replaces {last.supersedes.join(', ')}.
          The context revision is now {last.context_revision}, so earlier results are marked stale. Run the agent again.
        </Banner>
      ) : null}
      <table className="ledger" aria-label="Editable fictional facts" style={{ marginTop: 10 }}>
        <thead><tr><th>Fact</th><th>Creator</th><th>Current values</th><th>Source</th><th><span className="sr-only">Edit</span></th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td><strong>{r.kind === 'agreement' ? `Agreement with ${r.counterparty_name}` : 'Availability'}</strong><div className="mono">{r.id}</div></td>
              <td>{r.creator_name}<div className="mono">{r.creator_id}</div></td>
              <td>
                <div className="cell-note">{formatIst(r.start_ms)} → {formatIst(r.end_ms)}</div>
                <div className="cell-note">{r.status}{r.kind === 'agreement' ? ` · ${r.exclusive ? 'exclusive' : 'non-exclusive'} · ${r.channel}/${r.category}` : ''}</div>
                {editing === r.id && revision ? (
                  <Editor key={`${r.id}:${opened}`} row={r} revision={revision} campaignId={campaignId}
                    onCancel={() => setEditing(null)} onReload={() => { void onRefresh().then(() => setOpened((n) => n + 1)) }}
                    onDone={(res) => { setEditing(null); setLast(res) }} />
                ) : null}
              </td>
              <td><button type="button" className="btn link" onClick={() => onSource(r.source_id)}>v{r.version}</button></td>
              <td>{editing !== r.id ? <button type="button" className="btn small" onClick={() => { setEditing(r.id); setOpened((n) => n + 1); setLast(null) }} aria-label={`Edit ${r.id}`}>Edit</button> : null}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
