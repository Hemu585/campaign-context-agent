import { useState } from 'react'
import { ApiError } from '../api/client'
import { useRevoke } from '../api/hooks'
import type { CampaignSummary, Decision } from '../api/types'
import { formatIst } from '../lib/format'

const STATE: Record<string, { label: string; tone: string }> = {
  active: { label: 'Active', tone: 'memory' },
  expired: { label: 'Expired', tone: 'neutral' },
  revoked: { label: 'Revoked', tone: 'neutral' },
  not_yet_effective: { label: 'Not yet effective', tone: 'neutral' },
  approved: { label: 'Approved', tone: 'ok' },
  revoked_event: { label: 'Revocation', tone: 'neutral' },
}

function describe(d: Decision, campaign: CampaignSummary): string {
  if (d.action === 'approved') return `Approved the replacement proposal for ${d.creator_name}`
  if (d.action === 'revoked') return `Revoked the rejection of ${d.creator_name}`
  const scope = d.scope_type === 'brand' ? `every ${campaign.client_brand_name} campaign` : 'this campaign'
  return `Rejected ${d.creator_name} for ${scope}`
}

export function HistoryTab({ campaign, decisions, revision, onSource }: {
  campaign: CampaignSummary; decisions: Decision[]; revision: number | undefined; onSource: (id: string) => void
}) {
  const revoke = useRevoke(campaign.id)
  // Which rejection is being revoked, with the revision shown when the form opened.
  const [revoking, setRevoking] = useState<{ id: string; revision: number } | null>(null)
  const [reason, setReason] = useState('')
  const err = revoke.error instanceof ApiError ? revoke.error : null

  return (
    <div>
      <p className="scope-note">
        A <strong>campaign</strong> rejection applies only to {campaign.title}. A <strong>brand</strong> rejection applies to
        every {campaign.client_brand_name} campaign. Revoking or expiry stops filtering but keeps the record. Conversation
        text is never treated as a lasting preference; only these explicit actions are remembered.
      </p>
      {decisions.length === 0 ? <p className="cell-note">No decisions yet for this campaign or its brand.</p> : null}
      {decisions.map((d) => {
        const state = d.action === 'revoked' ? STATE.revoked_event : STATE[d.state] ?? { label: d.state, tone: 'neutral' }
        return (
          <div key={d.id} className="event">
            <span className={`chip tone-${state.tone}`}>{state.label}</span>
            <div className="what">
              {describe(d, campaign)} <span className="mono">({d.id})</span>
              <div className="cell-note">
                Recorded {formatIst(d.created_at_ms)} · business time {formatIst(d.as_of_ms)}
                {d.expires_at_ms ? <> · expires {formatIst(d.expires_at_ms)}</> : null}
                {d.campaign_title ? <> · campaign {d.campaign_title}{d.campaign_id !== campaign.id ? ' (another campaign)' : ''}</> : null}
                {d.revoked_by_id ? <> · revoked by <span className="mono">{d.revoked_by_id}</span></> : null}
              </div>
            </div>
            <div className="row-actions">
              {d.action === 'rejected' && d.is_active && revision ? (
                <button type="button" className="btn small" onClick={() => { setRevoking({ id: d.id, revision }); setReason(''); revoke.reset() }}>Revoke rejection</button>
              ) : null}
            </div>
            <div className="why">
              {d.reason ? <>Reason (as entered): “{d.reason}”</> : null}
              {d.source_ids.slice(0, 1).map((s) => (
                <span key={s}>{d.reason ? ' · ' : ''}<button type="button" className="btn link" onClick={() => onSource(s)}>Source record</button></span>
              ))}
              {revoking?.id === d.id ? (
                <form style={{ display: 'flex', gap: 6, marginTop: 6 }} onSubmit={(e) => {
                  e.preventDefault()
                  revoke.mutate({ decisionId: d.id, reason: reason.trim(), expected_revision: revoking.revision }, { onSuccess: () => setRevoking(null) })
                }}>
                  <label className="sr-only" htmlFor={`rv-${d.id}`}>Reason for revoking</label>
                  <input id={`rv-${d.id}`} className="select" style={{ flex: 1 }} required maxLength={500} placeholder="Why revoke?" value={reason} onChange={(e) => setReason(e.target.value)} />
                  <button type="submit" className="btn small primary" disabled={!reason.trim() || revoke.isPending}>Confirm revoke</button>
                  <button type="button" className="btn small ghost" onClick={() => setRevoking(null)}>Cancel</button>
                </form>
              ) : null}
              {revoking?.id === d.id && err ? <p className="error-text" role="alert">{err.message} ({err.code})</p> : null}
            </div>
          </div>
        )
      })}
    </div>
  )
}
