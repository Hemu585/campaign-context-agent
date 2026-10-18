// The single workspace screen: campaign case and agent conversation on the left, the evidence
// board (candidates, decision history, demo data) on the right. All results come from the backend;
// this file only chooses which run or rule check to show and whether it is still current.
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { ApiError } from './api/client'
import {
  qk, useBootstrap, useCampaign, useCampaigns, useCancelRun, useCreateSession, useDecisions, useFacts, useHealth,
  useProposals, useRuleCheck, useRun, useSession, useStartRun,
} from './api/hooks'
import type { CandidateEvaluation, Health, SessionDetail } from './api/types'
import { CampaignCard } from './components/CampaignCard'
import { CandidateTable } from './components/CandidateTable'
import { Conversation, SUGGESTED_PROMPT } from './components/Conversation'
import { DataEditorTab } from './components/DataEditorTab'
import { EvidenceDrawer } from './components/EvidenceDrawer'
import { Header } from './components/Header'
import { HistoryTab } from './components/HistoryTab'
import { ProposalDialog } from './components/ProposalDialog'
import { RejectDialog } from './components/RejectDialog'
import { SourceDialog } from './components/SourceViewer'
import { Banner } from './components/ui'
import { formatIst } from './lib/format'

const ACTIVE = new Set(['queued', 'running'])
// Errors already explained by the service banners, so other panels do not repeat them.
const SERVICE_CODES = new Set(['BACKEND_UNREACHABLE', 'GRAPH_UNAVAILABLE', 'NO_SEED_DATA'])
const SESSION_TITLE = 'Replacement review'
type BoardTab = 'candidates' | 'decisions' | 'data'
const TABS: { key: BoardTab; label: string }[] = [
  { key: 'candidates', label: 'Candidates' },
  { key: 'decisions', label: 'Decision history' },
  { key: 'data', label: 'Demo data' },
]

// Browser storage only remembers which campaign and session were open; it can be missing.
function stored(key: string): string | null {
  try { return localStorage.getItem(key) } catch { return null }
}
function store(key: string, value: string | null) {
  try { if (value) localStorage.setItem(key, value); else localStorage.removeItem(key) } catch { /* storage blocked */ }
}

function ServiceBanners({ health, error }: { health: Health | undefined; error: unknown }) {
  if (error instanceof ApiError && error.code === 'BACKEND_UNREACHABLE') {
    return (
      <Banner tone="error" title="The local backend is not answering.">
        Start it from the project root with <code>.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1</code>.
      </Banner>
    )
  }
  if (!health) return null
  return (
    <>
      {!health.graph.reachable ? (
        <Banner tone="error" title="FalkorDB is not reachable.">
          Start it with <code>docker compose up -d</code>. Nothing is shown from cached or in-memory data.
        </Banner>
      ) : !health.graph.seeded ? (
        <Banner tone="warn" title={`Graph ${health.graph.graph} has no demo data.`}>
          Seed it with <code>.\.venv\Scripts\python.exe -m app.cli seed --dataset demo_v1</code>.
        </Banner>
      ) : null}
      {!health.model.installed || !health.model.reachable ? (
        <Banner tone="warn" title="The local model is unavailable, so the agent cannot run.">
          {health.model.detail} Rule checks (no AI) still work.
        </Banner>
      ) : null}
    </>
  )
}

export default function App() {
  const qc = useQueryClient()
  const health = useHealth()
  const bootstrap = useBootstrap()
  const campaigns = useCampaigns()

  const [campaignId, setCampaignId] = useState<string | null>(() => stored('cca.campaign'))
  const [sessionId, setSessionId] = useState<string | null>(() => stored('cca.session'))
  const [view, setView] = useState<'run' | 'rule'>('run')
  const [tab, setTab] = useState<BoardTab>('candidates')
  const [evidenceFor, setEvidenceFor] = useState<string | null>(null)
  const [rejecting, setRejecting] = useState<CandidateEvaluation | null>(null)
  const [reviewing, setReviewing] = useState<string | null>(null)
  const [sourceId, setSourceId] = useState<string | null>(null)
  const tabRefs = useRef<Record<BoardTab, HTMLButtonElement | null>>({ candidates: null, decisions: null, data: null })

  // Fall back to the first campaign when nothing (or something no longer seeded) was remembered.
  useEffect(() => {
    const list = campaigns.data
    if (!list?.length) return
    if (!campaignId || !list.some((c) => c.id === campaignId)) setCampaignId(list[0]!.id)
  }, [campaigns.data, campaignId])
  useEffect(() => store('cca.campaign', campaignId), [campaignId])
  useEffect(() => store('cca.session', sessionId), [sessionId])

  const campaign = useCampaign(campaignId)
  const session = useSession(sessionId)
  const proposals = useProposals(campaignId)
  const decisions = useDecisions(campaignId)
  const facts = useFacts()

  // A remembered session that no longer exists (for example after a demo reset) is forgotten.
  useEffect(() => {
    if (session.error instanceof ApiError && session.error.code === 'SESSION_NOT_FOUND') setSessionId(null)
  }, [session.error])

  const createSession = useCreateSession((s: SessionDetail) => setSessionId(s.id))
  const startRun = useStartRun(sessionId)
  const cancelRun = useCancelRun()
  const ruleCheck = useRuleCheck()

  // Runs for this campaign in this session, oldest first. The newest drives progress; the newest
  // completed one supplies the results.
  const campaignRuns = (session.data?.runs ?? []).filter((r) => r.campaign_id === campaignId)
    .sort((a, b) => a.created_at_ms - b.created_at_ms)
  const latestRef = campaignRuns.at(-1)
  const latestRun = useRun(latestRef?.id ?? null)
  const lastDoneRef = [...campaignRuns].reverse().find((r) => r.status === 'completed')
  const doneId = latestRun.data?.status === 'completed' ? latestRun.data.id : lastDoneRef?.id ?? null
  const doneRun = useRun(doneId)

  // When the newest run finishes, refresh everything it may have changed (messages, draft, memory).
  const prevStatus = useRef<string | undefined>(undefined)
  useEffect(() => {
    const status = latestRun.data?.status
    if (prevStatus.current && ACTIVE.has(prevStatus.current) && status && !ACTIVE.has(status)) {
      for (const key of [qk.bootstrap, qk.campaigns]) void qc.invalidateQueries({ queryKey: key })
      if (sessionId) void qc.invalidateQueries({ queryKey: qk.session(sessionId) })
      if (campaignId) {
        for (const key of [qk.campaign(campaignId), qk.proposals(campaignId), qk.decisions(campaignId)]) {
          void qc.invalidateQueries({ queryKey: key })
        }
      }
      setView('run')
    }
    prevStatus.current = status
  }, [latestRun.data?.status, qc, sessionId, campaignId])

  const revision = bootstrap.data?.context_revision ?? undefined
  // A revision change made elsewhere (another tab, the CLI) refreshes every view of saved state, not
  // only the stale banner, so no form keeps showing facts that changed underneath it.
  const seenRevision = useRef(revision)
  useEffect(() => {
    if (revision === undefined) return
    if (seenRevision.current !== undefined && seenRevision.current !== revision) {
      for (const key of [qk.facts, qk.campaigns]) void qc.invalidateQueries({ queryKey: key })
      if (campaignId) {
        for (const key of [qk.campaign(campaignId), qk.proposals(campaignId), qk.decisions(campaignId)]) {
          void qc.invalidateQueries({ queryKey: key })
        }
      }
    }
    seenRevision.current = revision
  }, [revision, qc, campaignId])
  const runEval = doneRun.data?.evaluation ?? null
  const ruleEval = ruleCheck.data && ruleCheck.variables === campaignId ? ruleCheck.data : null
  const evaluation = view === 'rule' && ruleEval ? ruleEval : runEval ?? ruleEval
  const fromRun = !!runEval && evaluation === runEval
  const stale = !!evaluation && revision !== undefined && evaluation.context_revision !== revision
  const recommended = fromRun
    ? doneRun.data?.final?.recommended_creator_ids ?? evaluation!.recommended_creator_ids
    : evaluation?.recommended_creator_ids ?? []
  const draftId = fromRun ? doneRun.data?.proposal_id ?? doneRun.data?.final?.proposal_id ?? null : null
  const draft = proposals.data?.find((p) => p.id === draftId)
  const detail = campaign.data
  const approved = proposals.data?.find((p) => p.id === detail?.campaign.approved_proposal_id)
  const modelReady = !!health.data?.model.installed && !!health.data?.model.reachable
  const graphReady = !!health.data?.graph.reachable && !!health.data?.graph.seeded
  const blocked = !health.data ? (health.error ? 'The local backend is not answering, so the agent cannot run.' : 'Checking local services…')
    : !health.data.graph.reachable ? 'FalkorDB is not reachable, so the agent cannot run.'
      : !health.data.graph.seeded ? 'The graph has no demo data yet, so the agent cannot run.'
        : !modelReady ? 'The local model is unavailable, so the agent cannot run. Rule checks still work.' : null
  const evidenceCandidate = evaluation?.candidates.find((c) => c.creator_id === evidenceFor) ?? null
  const lastUserText = session.data?.messages.filter((m) => m.role === 'user' && campaignRuns.some((r) => r.id === m.run_id)).at(-1)?.text

  // The conversation shows this campaign's messages only; a session can span campaigns.
  const runIds = new Set(campaignRuns.map((r) => r.id))
  const conversationSession = session.data
    ? { ...session.data, messages: session.data.messages.filter((m) => !m.run_id || runIds.has(m.run_id)), runs: campaignRuns }
    : undefined

  const chooseCampaign = (id: string) => {
    setCampaignId(id)
    setView('run')
    setEvidenceFor(null)
    ruleCheck.reset()
    startRun.reset()
  }

  const runAgent = async (message: string) => {
    if (!campaignId) return
    startRun.reset()
    let sid = sessionId
    if (!sid) {
      try {
        sid = (await createSession.mutateAsync(SESSION_TITLE)).id
      } catch {
        return
      }
    }
    setView('run')
    startRun.mutate({ campaignId, message, sessionId: sid })
  }

  const onTabKey = (e: KeyboardEvent<HTMLButtonElement>) => {
    const i = TABS.findIndex((t) => t.key === tab)
    const next = e.key === 'ArrowRight' ? (i + 1) % TABS.length : e.key === 'ArrowLeft' ? (i + TABS.length - 1) % TABS.length
      : e.key === 'Home' ? 0 : e.key === 'End' ? TABS.length - 1 : -1
    if (next < 0) return
    e.preventDefault()
    setTab(TABS[next]!.key)
    tabRefs.current[TABS[next]!.key]?.focus()
  }

  const decisionCount = decisions.data?.length ?? 0

  return (
    <div className="app">
      <a className="skip-link" href="#board">Skip to the candidate board</a>
      <Header campaigns={campaigns.data ?? []} campaignId={campaignId} onCampaign={chooseCampaign}
        onNewSession={() => { createSession.mutate(SESSION_TITLE); setView('run'); setEvidenceFor(null) }}
        newSessionBusy={createSession.isPending} health={health.data} bootstrap={bootstrap.data} />

      <div className="banners">
        <ServiceBanners health={health.data} error={health.error} />
        {campaigns.error instanceof ApiError && !SERVICE_CODES.has(campaigns.error.code) ? (
          <Banner tone="error" title="Campaigns could not be loaded.">{campaigns.error.message} <span className="mono">({campaigns.error.code})</span></Banner>
        ) : null}
        {campaign.error instanceof ApiError && !SERVICE_CODES.has(campaign.error.code) ? (
          <Banner tone="error" title="This campaign could not be loaded."
            actions={<button type="button" className="btn small" onClick={() => void campaign.refetch()}>Retry</button>}>
            {campaign.error.message} Choose another campaign, or re-seed the graph if the demo data was reset.
          </Banner>
        ) : null}
        {createSession.error instanceof ApiError ? (
          <Banner tone="error" title="A new session could not be created.">{createSession.error.message}</Banner>
        ) : null}
      </div>

      <main className="workspace">
        <div className="column">
          <CampaignCard detail={detail} approved={approved} onSource={setSourceId} />
          <Conversation session={conversationSession} run={latestRun.data} blocked={blocked}
            starting={startRun.isPending || createSession.isPending} cancelling={cancelRun.isPending}
            startError={startRun.error} onRun={(m) => void runAgent(m)} onCancel={(id) => cancelRun.mutate(id)} />
        </div>

        <section className="card board" id="board" aria-label="Evidence board">
          <div className="tabs" role="tablist" aria-label="Board views">
            {TABS.map((t) => (
              <button key={t.key} ref={(el) => { tabRefs.current[t.key] = el }} type="button" role="tab" id={`tab-${t.key}`}
                className="tab" aria-selected={tab === t.key} aria-controls={`panel-${t.key}`} tabIndex={tab === t.key ? 0 : -1}
                onClick={() => setTab(t.key)} onKeyDown={onTabKey}>
                {t.label}
                {t.key === 'candidates' && evaluation ? <span className="count">{evaluation.candidates.length}</span> : null}
                {t.key === 'decisions' && decisionCount ? <span className="count">{decisionCount}</span> : null}
              </button>
            ))}
          </div>

          <div className="tabpanel" role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} tabIndex={0}>
            {tab === 'candidates' ? (
              <>
                <div className="context-line">
                  {evaluation ? (
                    <>
                      <span className={`chip ${fromRun ? 'tone-ok' : 'tone-neutral'}`}>
                        {fromRun ? `Agent run ${doneRun.data?.id}` : 'Rule check — no AI run'}
                      </span>
                      <span>As of {formatIst(evaluation.as_of_ms)}</span>
                      <span>Revision {evaluation.context_revision}</span>
                      {recommended.length > 0 ? <span className="legend"><span className="legend-bar" aria-hidden="true" />Recommended shortlist</span> : null}
                    </>
                  ) : <span>No results yet for this campaign.</span>}
                  <button type="button" className="btn small" style={{ marginLeft: 'auto' }}
                    disabled={!campaignId || !graphReady || ruleCheck.isPending}
                    onClick={() => { if (campaignId) ruleCheck.mutate(campaignId, { onSuccess: () => setView('rule') }) }}
                    title="Evaluate every candidate with the deterministic rules only. No model is called.">
                    {ruleCheck.isPending ? 'Checking…' : 'Rule check (no AI)'}
                  </button>
                  {view === 'rule' && runEval ? (
                    <button type="button" className="btn small ghost" onClick={() => setView('run')}>Show agent run result</button>
                  ) : null}
                </div>
                {ruleCheck.error instanceof ApiError ? (
                  <Banner tone="error" title="The rule check failed.">{ruleCheck.error.message} <span className="mono">({ruleCheck.error.code})</span></Banner>
                ) : null}
                {stale && detail?.campaign.approved_proposal_id ? (
                  <Banner tone="info" title="Slot filled after these results.">
                    They use revision {evaluation!.context_revision}; the current revision is {revision}. They stay here for reference.
                  </Banner>
                ) : stale ? (
                  <Banner tone="stale" title="Information changed — run again."
                    actions={
                      <button type="button" className="btn small primary" disabled={!!blocked || startRun.isPending || (!!latestRun.data && ACTIVE.has(latestRun.data.status))}
                        onClick={() => void runAgent(lastUserText ?? SUGGESTED_PROMPT)}>Run agent again</button>
                    }>
                    These results use revision {evaluation!.context_revision}; the current revision is {revision}. Drafts from them cannot be approved.
                  </Banner>
                ) : null}
                {evaluation ? (
                  <CandidateTable evaluation={evaluation} recommended={recommended} draft={draft} stale={stale}
                    onEvidence={setEvidenceFor} onReject={setRejecting} onReview={setReviewing} />
                ) : (
                  <div className="board-empty">
                    <p><strong>Run the agent</strong> to evaluate every creator against the graph, or use the rule check to see the deterministic result without a model.</p>
                    <p className="cell-note">Every status below will come from FalkorDB records and cite its sources.</p>
                  </div>
                )}
              </>
            ) : null}
            {tab === 'decisions' && detail ? (
              <HistoryTab campaign={detail.campaign} decisions={decisions.data ?? []} revision={revision} onSource={setSourceId} />
            ) : null}
            {tab === 'data' && campaignId ? (
              <DataEditorTab facts={facts.data} revision={revision} campaignId={campaignId} onSource={setSourceId}
                onRefresh={() => facts.refetch()} />
            ) : null}
          </div>
        </section>
      </main>

      <EvidenceDrawer candidate={evidenceCandidate} evaluation={evaluation} run={fromRun ? doneRun.data : undefined}
        onClose={() => setEvidenceFor(null)} />
      <RejectDialog candidate={rejecting} campaign={detail?.campaign} revision={revision} sessionId={sessionId}
        onClose={() => setRejecting(null)} />
      {campaignId ? (
        <ProposalDialog proposalId={reviewing} campaignId={campaignId} revision={revision}
          onClose={() => setReviewing(null)} onSource={setSourceId} />
      ) : null}
      <SourceDialog id={sourceId} onClose={() => setSourceId(null)} onOpen={setSourceId} />
    </div>
  )
}
