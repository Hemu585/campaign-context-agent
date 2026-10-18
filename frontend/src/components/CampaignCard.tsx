import type { CampaignDetail, Proposal } from '../api/types'
import { formatInr, formatIst, formatIstDate } from '../lib/format'
import { deliverableLabel, languageLabel } from '../lib/labels'

export function CampaignCard({ detail, approved, onSource }: {
  detail: CampaignDetail | undefined
  approved: Proposal | undefined
  onSource: (id: string) => void
}) {
  if (!detail) return <section className="card case" aria-busy="true">Loading campaign…</section>
  const c = detail.campaign
  return (
    <section className="card case" aria-labelledby="campaign-title">
      <div className="case-kicker">Replacement needed · {c.id}</div>
      <h2 id="campaign-title">{c.title}</h2>
      <div className="client">Client {c.client_brand_name} <span className="mono">({c.client_brand_id})</span></div>
      <div className="case-tags">
        <span className="tag">{deliverableLabel(c.deliverable)}</span>
        <span className="tag">{c.channel}</span>
        <span className="tag">{languageLabel(c.language)} content</span>
        <span className="tag">{c.category}</span>
      </div>
      <dl className="facts">
        <dt>Delivery</dt><dd>{formatIst(c.start_ms)} → {formatIst(c.end_ms)}</dd>
        <dt>Budget</dt><dd><strong>{formatInr(c.budget_paise)}</strong> for one replacement</dd>
        <dt>Dropped out</dt><dd>{c.dropped_creator_name} <span className="mono">({c.dropped_creator_id})</span></dd>
        <dt>Slot</dt>
        <dd>
          {c.approved_proposal_id
            ? <span className="slot-filled">✓ Filled by approved proposal {approved ? `for ${approved.creator_name}` : c.approved_proposal_id}</span>
            : <span className="slot-open">Open. Drafts are not approvals.</span>}
        </dd>
        <dt>Brief</dt>
        <dd>
          {detail.brief_sources.map((s) => (
            <button key={s.id} type="button" className="btn link" onClick={() => onSource(s.id)}>
              {s.id} (v{s.version}, observed {formatIstDate(s.observed_at_ms)})
            </button>
          ))}
        </dd>
      </dl>
    </section>
  )
}
