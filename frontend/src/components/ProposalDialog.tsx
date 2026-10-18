import { ApiError } from '../api/client'
import { useApprove, useProposal } from '../api/hooks'
import { formatInr, formatIst } from '../lib/format'
import { CHECK_LABEL, deliverableLabel, languageLabel } from '../lib/labels'
import { Banner, Dialog, ResultChip } from './ui'

export function ProposalDialog({ proposalId, campaignId, revision, onClose, onSource }: {
  proposalId: string | null; campaignId: string; revision: number | undefined; onClose: () => void; onSource: (id: string) => void
}) {
  const { data: p, refetch } = useProposal(proposalId)
  const approve = useApprove(campaignId)
  const result = approve.data
  const err = approve.error instanceof ApiError ? approve.error : null
  const snap = p?.snapshot
  const current = !!p && !p.is_stale && p.current_revision === revision
  const keyChecks = ['budget', 'availability', 'exclusivity', 'memory']

  return (
    <Dialog open={!!proposalId} onClose={() => { approve.reset(); onClose() }} labelledBy="proposal-title">
      <div className="dialog-head">
        <div>
          <h2 id="proposal-title">Review replacement proposal</h2>
          <div className="sub">{p ? <>Draft <span className="mono">{p.id}</span> from run <span className="mono">{p.run_id}</span></> : 'Loading…'}</div>
        </div>
        <button type="button" className="btn ghost close" onClick={() => { approve.reset(); onClose() }} aria-label="Close">✕</button>
      </div>
      {p && snap ? (
        <div className="dialog-body form-grid">
          <dl className="facts">
            <dt>Creator</dt><dd><strong>{p.creator_name}</strong> <span className="mono">({p.creator_id})</span></dd>
            <dt>Quoted fee</dt><dd><strong>{formatInr(snap.candidate.fee_paise)}</strong> within {formatInr(snap.campaign.budget_paise)}</dd>
            <dt>Campaign</dt><dd>{snap.campaign.title} · {snap.campaign.client_brand_name}</dd>
            <dt>Brief</dt><dd>{deliverableLabel(snap.campaign.deliverable)} · {languageLabel(snap.campaign.language)} · {snap.campaign.category} · {formatIst(snap.campaign.start_ms)} → {formatIst(snap.campaign.end_ms)}</dd>
            <dt>Evidence as of</dt><dd>{formatIst(snap.as_of_ms)} · revision {snap.context_revision}</dd>
            <dt>Information</dt>
            <dd>{p.status === 'approved' ? 'Saved decision (kept as recorded)' : current ? <ResultChip result="pass" label="Current" /> : <ResultChip result="fail" label="Changed since drafting" />}</dd>
          </dl>
          <ul className="checks two-up">
            {snap.candidate.checks.filter((c) => keyChecks.includes(c.name)).map((c) => (
              <li key={c.name}>
                <div className="row"><span className="label">{CHECK_LABEL[c.name]}</span><span style={{ marginLeft: 'auto' }}><ResultChip result={c.result} /></span></div>
                <div className="detail">{c.detail}</div>
              </li>
            ))}
          </ul>
          <details className="snapshot-sources">
            <summary>Evidence saved with this draft ({snap.sources.length} sources, {snap.evidence_paths.length} graph paths)</summary>
            <ul className="source-list">
              {snap.sources.map((s) => (
                <li key={s.id} className="excerpt">
                  <button type="button" className="btn link" onClick={() => onSource(s.id)}>{s.id}</button>
                  <span className="cell-note"> · {s.title} · v{s.version} · observed {formatIst(s.observed_at_ms)}</span>
                  <blockquote>{s.excerpt}</blockquote>
                </li>
              ))}
            </ul>
          </details>
          {p.status === 'draft' && !p.approvable ? (
            <Banner tone="stale" title="This draft cannot be approved.">
              {p.unusable_reason === 'stale' ? 'Information changed since it was drafted. Run the agent again.'
                : p.unusable_reason === 'slot_filled' ? 'The replacement slot already has an approved proposal.'
                  : 'Its agent run did not complete successfully.'}
            </Banner>
          ) : null}
          {result ? (
            <Banner tone="info" title="Approved and saved.">
              Decision <span className="mono">{result.decision_id}</span> recorded at {formatIst(result.proposal.approved_at_ms)}; the slot is filled
              (revision {result.context_revision}). Nothing was sent to the creator.
            </Banner>
          ) : null}
          {err ? (
            <Banner tone="error" title="Approval refused." actions={<button type="button" className="btn small" onClick={() => { approve.reset(); void refetch() }}>Refresh</button>}>
              {err.message} <span className="mono">({err.code})</span>
            </Banner>
          ) : null}
        </div>
      ) : <div className="dialog-body">Loading proposal…</div>}
      <div className="dialog-foot">
        <p className="statement foot-statement">Approves an internal replacement proposal. Does not contact or book the creator.</p>
        <button type="button" className="btn" onClick={() => { approve.reset(); onClose() }}>{result ? 'Close' : 'Not now'}</button>
        {p?.status === 'draft' && !result ? (
          <button type="button" className="btn primary" disabled={!p.approvable || !current || approve.isPending || !revision}
            onClick={() => approve.mutate({ proposalId: p.id, expected_revision: revision! }, { onError: () => void refetch() })}>
            {approve.isPending ? 'Approving…' : 'Approve proposal'}
          </button>
        ) : null}
      </div>
    </Dialog>
  )
}
