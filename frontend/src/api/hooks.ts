// TanStack Query hooks over the local API. Reads poll where the operator needs live state (service
// status, an active run); writes invalidate exactly the views they change.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef } from 'react'
import { WriteAttempts, classify } from './attempts'
import { ApiError, getJson, loadBootstrap, newKey, sendJson } from './client'
import type {
  ApprovalResult, Bootstrap, CampaignDetail, CampaignSummary, Decision, EditableFacts, EditResult, Evaluation, Health,
  Proposal, Run, SessionDetail, SourceDoc,
} from './types'

export const qk = {
  health: ['health'] as const,
  bootstrap: ['bootstrap'] as const,
  campaigns: ['campaigns'] as const,
  campaign: (id: string) => ['campaign', id] as const,
  session: (id: string) => ['session', id] as const,
  run: (id: string) => ['run', id] as const,
  proposals: (campaignId: string) => ['proposals', campaignId] as const,
  proposal: (id: string) => ['proposal', id] as const,
  decisions: (campaignId: string) => ['decisions', campaignId] as const,
  facts: ['facts'] as const,
  source: (id: string) => ['source', id] as const,
}

const ACTIVE = new Set(['queued', 'running'])

export function useHealth() {
  return useQuery({ queryKey: qk.health, queryFn: () => getJson<Health>('/api/health', { allow503: true }), refetchInterval: 10_000 })
}

export function useBootstrap() {
  return useQuery({ queryKey: qk.bootstrap, queryFn: loadBootstrap, refetchInterval: 15_000 })
}

export function useCampaigns() {
  return useQuery({ queryKey: qk.campaigns, queryFn: () => getJson<CampaignSummary[]>('/api/campaigns') })
}

export function useCampaign(id: string | null) {
  return useQuery({ queryKey: qk.campaign(id ?? ''), queryFn: () => getJson<CampaignDetail>(`/api/campaigns/${id}`), enabled: !!id })
}

export function useSession(id: string | null) {
  return useQuery({ queryKey: qk.session(id ?? ''), queryFn: () => getJson<SessionDetail>(`/api/sessions/${id}`), enabled: !!id })
}

export function useRun(id: string | null) {
  return useQuery({
    queryKey: qk.run(id ?? ''),
    queryFn: () => getJson<Run>(`/api/runs/${id}`),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data && ACTIVE.has(q.state.data.status) ? 1000 : false),
  })
}

export function useProposals(campaignId: string | null) {
  return useQuery({ queryKey: qk.proposals(campaignId ?? ''), queryFn: () => getJson<Proposal[]>(`/api/proposals?campaign_id=${campaignId}`), enabled: !!campaignId })
}

export function useProposal(id: string | null) {
  return useQuery({ queryKey: qk.proposal(id ?? ''), queryFn: () => getJson<Proposal>(`/api/proposals/${id}`), enabled: !!id })
}

export function useDecisions(campaignId: string | null) {
  return useQuery({ queryKey: qk.decisions(campaignId ?? ''), queryFn: () => getJson<Decision[]>(`/api/decisions?campaign_id=${campaignId}`), enabled: !!campaignId })
}

export function useFacts() {
  return useQuery({ queryKey: qk.facts, queryFn: () => getJson<EditableFacts>('/api/demo/facts') })
}

export function useSource(id: string | null) {
  return useQuery({ queryKey: qk.source(id ?? ''), queryFn: () => getJson<SourceDoc>(`/api/sources/${id}`), enabled: !!id, staleTime: Infinity })
}

/**
 * A write with one Idempotency-Key per user action (see attempts.ts): double clicks and retries after
 * an unknown outcome resend the same payload under the same key; only success or a refusal that
 * proves nothing was written starts the next action fresh.
 */
function useWrite<TArgs, TResult>(send: (args: TArgs, key: string) => Promise<TResult>, onDone?: (r: TResult, a: TArgs) => void) {
  const qc = useQueryClient()
  const attempts = useRef<WriteAttempts<TArgs> | null>(null)
  attempts.current ??= new WriteAttempts<TArgs>(newKey)
  const sent = useRef<TArgs | null>(null)
  return useMutation({
    mutationFn: (args: TArgs) => {
      const { key, payload } = attempts.current!.begin(args)
      sent.current = payload
      return send(payload, key)
    },
    onSuccess: (result) => {
      attempts.current!.settle('success')
      onDone?.(result, sent.current!)
    },
    onError: (err) => {
      attempts.current!.settle(classify(err))
      if (err instanceof ApiError && err.status === 409) void qc.invalidateQueries({ queryKey: qk.bootstrap })
    },
  })
}

export function useCreateSession(onCreated: (s: SessionDetail) => void) {
  const qc = useQueryClient()
  return useWrite((title: string, key) => sendJson<SessionDetail>('POST', '/api/sessions', { title }, key), (s) => {
    qc.setQueryData(qk.session(s.id), s)
    onCreated(s)
  })
}

export function useStartRun(sessionId: string | null) {
  const qc = useQueryClient()
  return useWrite(
    (args: { campaignId: string; message: string; sessionId?: string }, key) =>
      sendJson<Run>('POST', `/api/sessions/${args.sessionId ?? sessionId}/runs`, { campaign_id: args.campaignId, message: args.message }, key),
    (run) => {
      qc.setQueryData(qk.run(run.id), run)
      void qc.invalidateQueries({ queryKey: qk.session(run.session_id) })
    },
  )
}

export function useCancelRun() {
  const qc = useQueryClient()
  return useWrite((runId: string, key) => sendJson<Run>('POST', `/api/runs/${runId}/cancel`, {}, key), (run) => {
    qc.setQueryData(qk.run(run.id), run)
    void qc.invalidateQueries({ queryKey: qk.session(run.session_id) })
  })
}

export function useRuleCheck() {
  return useWrite((campaignId: string, key) => sendJson<Evaluation>('POST', `/api/campaigns/${campaignId}/evaluate`, {}, key))
}

function invalidateContext(qc: ReturnType<typeof useQueryClient>, campaignId: string) {
  for (const key of [qk.bootstrap, qk.campaigns, qk.campaign(campaignId), qk.proposals(campaignId), qk.decisions(campaignId), qk.facts]) {
    void qc.invalidateQueries({ queryKey: key })
  }
  void qc.invalidateQueries({ queryKey: ['proposal'] })
  void qc.invalidateQueries({ queryKey: ['decisions'] })
}

export type RejectArgs = {
  campaign_id: string; creator_id: string; scope_type: 'campaign' | 'brand'; reason: string
  expires_at_ms: number | null; expected_revision: number; session_id: string | null
}

export function useReject() {
  const qc = useQueryClient()
  return useWrite((args: RejectArgs, key) => sendJson<Decision>('POST', '/api/decisions/rejections', args, key),
    (_d, args) => invalidateContext(qc, args.campaign_id))
}

export function useRevoke(campaignId: string) {
  const qc = useQueryClient()
  return useWrite((args: { decisionId: string; reason: string; expected_revision: number }, key) =>
    sendJson<Decision>('POST', `/api/decisions/${args.decisionId}/revoke`, { reason: args.reason, expected_revision: args.expected_revision }, key),
  () => invalidateContext(qc, campaignId))
}

export function useEditFact(campaignId: string) {
  const qc = useQueryClient()
  return useWrite((args: { type: 'agreement' | 'availability'; id: string; changes: Record<string, unknown>; reason: string; expected_revision: number }, key) =>
    sendJson<EditResult>('PATCH', `/api/demo/facts/${args.type}/${args.id}`, { changes: args.changes, reason: args.reason, expected_revision: args.expected_revision }, key),
  () => invalidateContext(qc, campaignId))
}

export function useApprove(campaignId: string) {
  const qc = useQueryClient()
  return useWrite((args: { proposalId: string; expected_revision: number }, key) =>
    sendJson<ApprovalResult>('POST', `/api/proposals/${args.proposalId}/approve`, { expected_revision: args.expected_revision }, key),
  (result) => {
    qc.setQueryData(qk.proposal(result.proposal.id), result.proposal)
    invalidateContext(qc, campaignId)
  })
}

export type { Bootstrap }
