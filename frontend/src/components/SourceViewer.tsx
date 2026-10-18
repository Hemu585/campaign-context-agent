import { useSource } from '../api/hooks'
import { formatIst } from '../lib/format'
import { Dialog } from './ui'

/** Read-only fictional source document. Text is rendered as text, never as HTML. */
export function SourceViewer({ id, onOpen }: { id: string; onOpen: (id: string) => void }) {
  const { data, error, isLoading } = useSource(id)
  if (isLoading) return <p className="cell-note">Loading {id}…</p>
  if (error || !data) return <p className="error-text">Could not load source {id}.</p>
  return (
    <article aria-label={`Source ${data.id}`}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
        <strong style={{ fontFamily: 'var(--serif)' }}>{data.title}</strong>
        <span className="tag">version {data.version}</span>
        <span className={`chip ${data.verified ? 'tone-ok' : 'tone-bad'}`}>{data.verified ? 'Verified' : 'Unverified'}</span>
        <span className="chip tone-neutral">{data.fictional_label}</span>
      </div>
      <div className="cell-note" style={{ marginTop: 4 }}>
        <span className="mono">{data.id}</span> · observed {formatIst(data.observed_at_ms)}
        {data.editor ? <> · attested by {data.editor}</> : null}
      </div>
      {data.superseded_by.length > 0 ? (
        <p className="banner stale" style={{ marginTop: 8 }}>
          A newer version exists: {data.superseded_by.map((s) => <button key={s} type="button" className="btn link" onClick={() => onOpen(s)}>{s}</button>)}.
          Saved decisions keep citing the version they used.
        </p>
      ) : null}
      {data.supersedes.length > 0 ? (
        <p className="cell-note">Replaces {data.supersedes.map((s) => <button key={s} type="button" className="btn link" onClick={() => onOpen(s)}>{s}</button>)}</p>
      ) : null}
      <pre className="source-doc">{data.text}</pre>
    </article>
  )
}

export function SourceDialog({ id, onClose, onOpen }: { id: string | null; onClose: () => void; onOpen: (id: string) => void }) {
  return (
    <Dialog open={!!id} onClose={onClose} labelledBy="source-title">
      <div className="dialog-head">
        <div><h2 id="source-title">Source document</h2><div className="sub">Read-only fictional record stored in FalkorDB</div></div>
        <button type="button" className="btn ghost close" onClick={onClose} aria-label="Close source">✕</button>
      </div>
      <div className="dialog-body">{id ? <SourceViewer id={id} onOpen={onOpen} /> : null}</div>
    </Dialog>
  )
}
