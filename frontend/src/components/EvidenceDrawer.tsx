import { useEffect, useMemo, useState } from 'react'
import type { CandidateEvaluation, Evaluation, Run } from '../api/types'
import { elapsed, formatInr, formatIstDate } from '../lib/format'
import { CHECK_LABEL, TOOL_LABEL, reasonLabel } from '../lib/labels'
import { PathDiagram, PathList } from './PathDiagram'
import { SourceViewer } from './SourceViewer'
import { Dialog, ResultChip, SourceChip, StatusChip } from './ui'

type Tab = 'checks' | 'paths' | 'sources' | 'activity'

export function EvidenceDrawer({ candidate, evaluation, run, onClose }: {
  candidate: CandidateEvaluation | null
  evaluation: Evaluation | null
  run: Run | undefined
  onClose: () => void
}) {
  const [tab, setTab] = useState<Tab>('checks')
  const [sourceId, setSourceId] = useState<string | null>(null)

  useEffect(() => {
    setTab('checks')
    setSourceId(null)
  }, [candidate?.creator_id])

  const paths = useMemo(() => {
    if (!candidate || !evaluation) return []
    const problems = new Set(candidate.checks.filter((c) => c.result === 'fail' || c.result === 'unknown').map((c) => c.name))
    return evaluation.evidence_paths
      .filter((p) => candidate.evidence_path_ids.includes(p.id))
      .sort((a, b) => Number(!problems.has(a.check)) - Number(!problems.has(b.check)))
  }, [candidate, evaluation])

  const sourceIds = useMemo(() => {
    if (!candidate) return []
    const ids = new Set<string>()
    candidate.checks.forEach((c) => c.source_ids.forEach((s) => ids.add(s)))
    paths.forEach((p) => p.source_ids.forEach((s) => ids.add(s)))
    candidate.completed_campaigns.forEach((h) => ids.add(h.source_id))
    return [...ids].sort()
  }, [candidate, paths])

  const meta = new Map((evaluation?.sources ?? []).map((s) => [s.id, s]))
  const openSource = (id: string) => { setSourceId(id); setTab('sources') }
  const trace = run?.trace ?? []
  const problems = new Set(candidate?.checks.filter((c) => c.result === 'fail' || c.result === 'unknown').map((c) => c.name))

  return (
    <Dialog open={!!candidate} onClose={onClose} className="drawer" labelledBy="evidence-title">
      {candidate ? (
        <>
          <div className="dialog-head">
            <div>
              <h2 id="evidence-title">{candidate.name} <span className="mono">({candidate.creator_id})</span></h2>
              <div className="sub" style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginTop: 6 }}>
                <StatusChip status={candidate.status} />
                <span>Fee {formatInr(candidate.fee_paise)}</span>
                {candidate.rank ? <span>Rank {candidate.rank}</span> : null}
                <span>{candidate.completed_campaign_count} completed campaigns</span>
                {evaluation ? <span className="cell-note">revision {evaluation.context_revision}</span> : null}
              </div>
            </div>
            <button type="button" className="btn ghost close" onClick={onClose} aria-label="Close evidence">✕</button>
          </div>
          <div className="tabs" role="tablist" aria-label="Evidence views">
            {([['checks', 'Checks'], ['paths', `Graph paths`], ['sources', 'Sources'], ['activity', 'Tool activity']] as [Tab, string][]).map(([key, label]) => (
              <button key={key} type="button" role="tab" className="tab" aria-selected={tab === key} onClick={() => setTab(key)}>
                {label}{key === 'paths' ? <span className="count">{paths.length}</span> : key === 'sources' ? <span className="count">{sourceIds.length}</span> : null}
              </button>
            ))}
          </div>
          <div className="dialog-body" role="tabpanel">
            {tab === 'checks' ? (
              <ul className="checks">
                {/* Checks that explain the status come first; the rest keep the rule order. */}
                {[...candidate.checks].sort((a, b) => Number(!problems.has(a.name)) - Number(!problems.has(b.name))).map((c) => (
                  <li key={c.name}>
                    <div className="row">
                      <span className="label">{CHECK_LABEL[c.name] ?? c.name}</span>
                      <span style={{ marginLeft: 'auto' }}><ResultChip result={c.result} label={c.result === 'pass' ? 'Pass' : c.reason_code ? reasonLabel(c.reason_code) : undefined} /></span>
                    </div>
                    <div className="detail">{c.detail}</div>
                    {c.source_ids.length > 0 ? <div className="srcs">{c.source_ids.map((s) => <SourceChip key={s} id={s} onOpen={openSource} />)}</div> : null}
                  </li>
                ))}
                <li>
                  <div className="row">
                    <span className="label">Completed campaigns</span>
                    <span style={{ marginLeft: 'auto' }} className="cell-note">{candidate.completed_campaign_count} verified</span>
                  </div>
                  <div className="detail">
                    Used only to break a fee tie (then the ID decides).
                    {candidate.completed_campaigns.length > 0 ? <> Counted: <span className="mono">{candidate.completed_campaigns.map((h) => h.campaign_id).join(', ')}</span>.</> : null}
                  </div>
                  {candidate.completed_campaigns.length > 0 ? (
                    <div className="srcs">{candidate.completed_campaigns.map((h) => <SourceChip key={h.source_id} id={h.source_id} onOpen={openSource} />)}</div>
                  ) : null}
                </li>
              </ul>
            ) : null}
            {tab === 'paths' ? (
              <div className="chain">
                {paths.length === 0 ? <p className="cell-note">No graph paths recorded for this creator.</p> : paths.map((p) => (
                  <figure key={p.id}>
                    <figcaption>
                      {CHECK_LABEL[p.check] ?? p.check}
                      {problems.has(p.check) ? <span className="chip tone-bad">explains the result</span> : null}
                    </figcaption>
                    <PathDiagram path={p} hot={problems.has(p.check)} />
                    <PathList path={p} onSource={openSource} />
                  </figure>
                ))}
              </div>
            ) : null}
            {tab === 'sources' ? (
              <div style={{ display: 'grid', gap: 12 }}>
                <ul className="source-list" aria-label="Sources cited for this creator">
                  {sourceIds.map((id) => {
                    const m = meta.get(id)
                    return (
                      <li key={id}>
                        <button type="button" aria-pressed={sourceId === id} onClick={() => setSourceId(id)}>
                          <span className="mono">{id}</span>{m ? <> · {m.title} · v{m.version} · observed {formatIstDate(m.observed_at_ms)}{m.superseded ? ' · superseded' : ''}</> : null}
                        </button>
                      </li>
                    )
                  })}
                </ul>
                {sourceId ? <SourceViewer id={sourceId} onOpen={setSourceId} /> : <p className="cell-note">Choose a source to read the full fictional document.</p>}
              </div>
            ) : null}
            {tab === 'activity' ? (
              trace.length === 0 ? <p className="cell-note">{run ? 'No tool activity recorded yet.' : 'This view comes from a rule check, so there was no agent run.'}</p> : (
                <table className="ledger trace" aria-label="Tool activity">
                  <thead><tr><th>#</th><th>Step</th><th>Status</th><th className="num">Time</th><th>Records / queries</th></tr></thead>
                  <tbody>
                    {trace.map((t) => (
                      <tr key={t.seq}>
                        <td className="num">{t.seq}</td>
                        <td>
                          {t.type === 'tool' ? (TOOL_LABEL[t.tool ?? ''] ?? t.tool) : t.type === 'model' ? `Model turn ${t.turn} (${t.purpose})` : 'Answer validation'}
                          {t.type === 'tool' ? <div className="mono">{t.tool}{t.args && Object.keys(t.args).length ? ` ${JSON.stringify(t.args)}` : ''}</div> : null}
                        </td>
                        <td>
                          {t.type === 'tool' ? (t.status === 'ok' ? <ResultChip result="pass" label="ok" /> : <ResultChip result="fail" label={t.error_code ?? 'error'} />) : null}
                          {t.type === 'model' ? <span className="cell-note">{t.tool_calls?.length ? `asked for ${t.tool_calls.join(', ')}` : 'finished'}</span> : null}
                          {t.type === 'validation' ? (t.problems?.length ? <ResultChip result="unknown" label={`${t.problems.length} problem(s), repaired`} /> : <ResultChip result="pass" label="valid" />) : null}
                        </td>
                        <td className="num">{elapsed(t.elapsed_ms)}</td>
                        <td className="mono">{[...(t.record_ids ?? []).slice(0, 6), ...(t.query_ids ?? [])].join(' ')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )
            ) : null}
          </div>
        </>
      ) : null}
    </Dialog>
  )
}
