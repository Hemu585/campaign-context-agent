import type { CandidateEvaluation, Check, Evaluation, Proposal } from '../api/types'
import { formatInr } from '../lib/format'
import { reasonLabel } from '../lib/labels'
import { Avatar, ResultChip, StatusChip } from './ui'

const GROUPS: { status: CandidateEvaluation['status']; title: string }[] = [
  { status: 'eligible', title: 'Eligible · ranked by fee, then completed campaigns, then ID' },
  { status: 'excluded_by_memory', title: 'Excluded by your remembered rejections' },
  { status: 'unknown', title: 'Needs information · evidence missing or stale, never treated as clear' },
  { status: 'ineligible', title: 'Ineligible · a hard rule fails' },
]

function check(c: CandidateEvaluation, name: string): Check | undefined {
  return c.checks.find((ch) => ch.name === name)
}

function AvailabilityCell({ c }: { c: CandidateEvaluation }) {
  const ch = check(c, 'availability')
  if (!ch) return null
  if (ch.result === 'pass') return <ResultChip result="pass" label="Available" />
  if (ch.result === 'fail') return <ResultChip result="fail" label="Unavailable" />
  return <ResultChip result="unknown" />
}

function ConflictCell({ c }: { c: CandidateEvaluation }) {
  const ch = check(c, 'exclusivity')
  if (!ch) return null
  if (ch.result === 'pass') return <span className="cell-note">No conflict found in verified demo records</span>
  if (ch.result === 'fail') return <ResultChip result="fail" label="Competitor exclusivity" />
  if (ch.result === 'unknown') return <ResultChip result="unknown" label="Cannot rule out" />
  return <span className="cell-note">–</span>
}

function MemoryCell({ c }: { c: CandidateEvaluation }) {
  const ch = check(c, 'memory')
  if (ch?.result !== 'fail') return <span className="cell-note">–</span>
  const scope = ch.facts?.scope_type === 'brand' ? 'brand' : 'campaign'
  return (
    <>
      <span className="chip tone-memory"><span className="glyph" aria-hidden="true">⊘</span>Rejected</span>
      <div className="cell-note">{scope} scope</div>
    </>
  )
}

export function CandidateTable({ evaluation, recommended, draft, stale, onEvidence, onReject, onReview }: {
  evaluation: Evaluation
  recommended: string[]
  draft: Proposal | undefined
  stale: boolean
  onEvidence: (creatorId: string) => void
  onReject: (c: CandidateEvaluation) => void
  onReview: (proposalId: string) => void
}) {
  return (
    <table className="ledger" aria-label="Replacement candidates">
      <thead>
        <tr>
          <th scope="col">Rank</th><th scope="col">Creator and status</th><th scope="col" className="num">Fee</th>
          <th scope="col">Availability</th><th scope="col">Competitor conflict</th><th scope="col">Memory</th>
          <th scope="col"><span className="sr-only">Actions</span></th>
        </tr>
      </thead>
      <tbody>
        {evaluation.candidates.every((c) => c.status !== 'eligible') ? (
          <tr className="group"><td colSpan={7}>No eligible candidate · every creator fails a hard rule, needs information or was rejected, so nothing can be staged</td></tr>
        ) : null}
        {GROUPS.map((g) => {
          const rows = evaluation.candidates.filter((c) => c.status === g.status)
          if (rows.length === 0) return null
          return [
            <tr key={`g-${g.status}`} className="group"><td colSpan={7}>{g.title} ({rows.length})</td></tr>,
            ...rows.map((c, i) => {
              const reasons = c.checks.filter((ch) => (ch.result === 'fail' || ch.result === 'unknown') && ch.reason_code)
              const isDraft = draft && draft.creator_id === c.creator_id && draft.status === 'draft'
              return (
                <tr key={c.creator_id} className={`row-in ${recommended.includes(c.creator_id) ? 'recommended' : ''}`}
                  style={{ animationDelay: `${i * 30}ms` }}>
                  <td>{c.rank ? <span className="rank" aria-label={`Rank ${c.rank}`}>{c.rank}</span> : <span className="cell-note">–</span>}</td>
                  <td>
                    <div className="who">
                      <Avatar name={c.name} />
                      <div>
                        <div className="name-line"><span className="name">{c.name}</span><StatusChip status={c.status} /></div>
                        <div className="mono">{c.creator_id} · {c.completed_campaign_count} completed</div>
                        {reasons.length > 0 ? (
                          <div className="reasons">
                            {reasons.map((r) => <span key={r.name} className={`chip tone-${r.result === 'fail' ? 'bad' : 'unknown'}`}>{reasonLabel(r.reason_code)}</span>)}
                          </div>
                        ) : null}
                      </div>
                    </div>
                  </td>
                  <td className="num">{formatInr(c.fee_paise)}</td>
                  <td><AvailabilityCell c={c} /></td>
                  <td><ConflictCell c={c} /></td>
                  <td><MemoryCell c={c} /></td>
                  <td>
                    <div className="row-actions">
                      <button type="button" className="btn small" onClick={() => onEvidence(c.creator_id)}
                        aria-label={`View evidence for ${c.name}`}>View evidence</button>
                      {isDraft ? (
                        <button type="button" className="btn small primary" onClick={() => onReview(draft!.id)}
                          disabled={stale} title={stale ? 'Information changed. Run the agent again.' : undefined}>
                          Review proposal
                        </button>
                      ) : null}
                      {c.status !== 'excluded_by_memory' ? (
                        <button type="button" className="btn small ghost" onClick={() => onReject(c)}
                          aria-label={`Reject ${c.name}`}>Reject</button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              )
            }),
          ]
        })}
      </tbody>
    </table>
  )
}
