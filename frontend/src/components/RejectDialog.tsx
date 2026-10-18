import { useState } from 'react'
import { ApiError } from '../api/client'
import { useReject } from '../api/hooks'
import type { CampaignSummary, CandidateEvaluation } from '../api/types'
import { istInputToMs, parseIstInput } from '../lib/format'
import { Dialog } from './ui'

function RejectForm({ candidate, campaign, revision, sessionId, onClose }: {
  candidate: CandidateEvaluation; campaign: CampaignSummary; revision: number; sessionId: string | null; onClose: () => void
}) {
  // The decision is made on the information shown when the dialog opened (Review fix C1/C2).
  const [baseRevision] = useState(revision)
  const [scope, setScope] = useState<'campaign' | 'brand'>('campaign')
  const [reason, setReason] = useState('')
  const [expiry, setExpiry] = useState('')
  const reject = useReject()
  const err = reject.error instanceof ApiError ? reject.error : null

  return (
    <form onSubmit={(e) => {
      e.preventDefault()
      reject.mutate({
        campaign_id: campaign.id, creator_id: candidate.creator_id, scope_type: scope, reason: reason.trim(),
        expires_at_ms: expiry ? istInputToMs(expiry) : null, expected_revision: baseRevision, session_id: sessionId,
      }, { onSuccess: onClose })
    }}>
      <div className="dialog-head">
        <div>
          <h2 id="reject-title">Reject {candidate.name}</h2>
          <div className="sub">Remembered across sessions. Revoke it any time from Decision history.</div>
        </div>
        <button type="button" className="btn ghost close" onClick={onClose} aria-label="Close">✕</button>
      </div>
      <div className="dialog-body form-grid">
        <fieldset>
          <legend>Where should this rejection apply?</legend>
          <label className="radio">
            <input type="radio" name="scope" value="campaign" checked={scope === 'campaign'} onChange={() => setScope('campaign')} />
            <span>This campaign only: <strong>{campaign.title}</strong></span>
          </label>
          <label className="radio">
            <input type="radio" name="scope" value="brand" checked={scope === 'brand'} onChange={() => setScope('brand')} />
            <span>Every campaign of <strong>{campaign.client_brand_name}</strong>, including future ones</span>
          </label>
        </fieldset>
        <label>
          Reason <span className="hint">Required. Stored as data; it never widens the scope you chose.</span>
          <textarea data-autofocus required maxLength={500} rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
        </label>
        <label>
          Expires (optional, IST) <span className="hint">After this moment the rejection stops filtering but stays in history.</span>
          <input type="datetime-local" value={expiry} onChange={(e) => setExpiry(e.target.value)} />
        </label>
        {expiry && parseIstInput(expiry) === null ? <p className="error-text" role="alert">Enter a complete expiry date and time, or clear it.</p> : null}
        {err ? <p className="error-text" role="alert">{err.message} ({err.code})</p> : null}
      </div>
      <div className="dialog-foot">
        <button type="button" className="btn" onClick={onClose}>Cancel</button>
        <button type="submit" className="btn primary" disabled={!reason.trim() || reject.isPending || (!!expiry && parseIstInput(expiry) === null)}>
          {reject.isPending ? 'Saving…' : 'Save rejection'}
        </button>
      </div>
    </form>
  )
}

export function RejectDialog(props: {
  candidate: CandidateEvaluation | null; campaign: CampaignSummary | undefined; revision: number | undefined
  sessionId: string | null; onClose: () => void
}) {
  const { candidate, campaign, revision } = props
  return (
    <Dialog open={!!candidate} onClose={props.onClose} labelledBy="reject-title">
      {candidate && campaign && revision ? (
        <RejectForm key={candidate.creator_id} candidate={candidate} campaign={campaign} revision={revision}
          sessionId={props.sessionId} onClose={props.onClose} />
      ) : null}
    </Dialog>
  )
}
