// Human wording for statuses, checks, reason codes and run phases. Every status pairs a glyph with
// words, so colour is never the only signal (UI_REQUIREMENTS accessibility).

export const STATUS = {
  eligible: { label: 'Eligible', glyph: '✓', tone: 'ok' },
  ineligible: { label: 'Ineligible', glyph: '✕', tone: 'bad' },
  unknown: { label: 'Needs information', glyph: '?', tone: 'unknown' },
  excluded_by_memory: { label: 'Excluded by your rejection', glyph: '⊘', tone: 'memory' },
} as const

export const RESULT = {
  pass: { label: 'Pass', glyph: '✓', tone: 'ok' },
  fail: { label: 'Fails', glyph: '✕', tone: 'bad' },
  unknown: { label: 'Needs information', glyph: '?', tone: 'unknown' },
  not_applicable: { label: 'Not applicable', glyph: '–', tone: 'neutral' },
} as const

export const CHECK_LABEL: Record<string, string> = {
  participation: 'Roster',
  offer_match: 'Exact offer',
  quote_validity: 'Quote dates',
  budget: 'Budget',
  availability: 'Availability',
  agreement_audit: 'Agreement audit',
  competitor_audit: 'Competitor map',
  exclusivity: 'Competitor conflict',
  memory: 'Your rejections',
}

export const REASON_LABEL: Record<string, string> = {
  DROPPED_OUT: 'Dropped out',
  CURRENTLY_ASSIGNED: 'Already assigned',
  INACTIVE_CREATOR: 'Inactive',
  NO_MATCHING_OFFER: 'No matching offer',
  OFFER_CURRENCY_MISMATCH: 'Wrong currency',
  MULTIPLE_MATCHING_OFFERS: 'Conflicting quotes',
  QUOTE_EXPIRED: 'Quote expired',
  QUOTE_NOT_YET_VALID: 'Quote not yet valid',
  QUOTE_DATES_MISSING: 'Quote dates missing',
  OVER_BUDGET: 'Over budget',
  FEE_MISSING: 'Fee missing',
  UNAVAILABLE_OVERLAP: 'Unavailable',
  NO_COVERING_WINDOW: 'Partial availability',
  NO_AVAILABILITY_RECORD: 'No availability record',
  AUDIT_MISSING: 'Audit missing',
  AUDIT_INCOMPLETE: 'Audit incomplete',
  AUDIT_COVERAGE: 'Audit does not cover window',
  AUDIT_LIST_MISMATCH: 'Audit out of date',
  COMPETITOR_EXCLUSIVITY: 'Competitor exclusivity',
  AGREEMENT_DATES_MISSING: 'Agreement dates missing',
  AGREEMENT_SCOPE_MISSING: 'Agreement scope missing',
  AGREEMENT_FIELDS_MISSING: 'Agreement fields missing',
  AGREEMENT_COUNTERPARTY_MISSING: 'Counterparty missing',
  REQUIRES_COMPLETE_AUDITS: 'Cannot rule out conflicts',
  REJECTED_BY_OPERATOR: 'Rejected by you',
  STALE_SOURCE: 'Evidence too old',
  FUTURE_SOURCE: 'Evidence future-dated',
  UNVERIFIED_SOURCE: 'Evidence unverified',
  SUPERSEDED_SOURCE: 'Evidence superseded',
  MISSING_SOURCE: 'Evidence missing',
  CONFLICTING_SOURCES: 'Sources disagree',
  SOURCE_MISMATCH: 'Record differs from source',
}

export const PHASE_LABEL: Record<string, string> = {
  queued: 'Waiting to start',
  reading_campaign: 'Reading the campaign',
  checking_candidates: 'Checking every candidate',
  reviewing_memory: 'Reviewing remembered decisions',
  inspecting_evidence: 'Inspecting evidence',
  preparing_proposal: 'Preparing a draft proposal',
  writing_summary: 'Writing the summary',
  done: 'Done',
}

export const TOOL_LABEL: Record<string, string> = {
  get_campaign_requirements: 'Read campaign requirements',
  evaluate_candidates: 'Evaluated every candidate',
  get_candidate_evidence: 'Inspected evidence',
  get_previous_decisions: 'Reviewed remembered decisions',
  stage_replacement_proposal: 'Staged a draft proposal',
}

export const RUN_STATUS_LABEL: Record<string, string> = {
  queued: 'Queued',
  running: 'Running',
  completed: 'Completed',
  needs_clarification: 'Needs clarification',
  failed: 'Failed',
  cancelled: 'Cancelled',
  interrupted: 'Interrupted by a restart',
}

export function reasonLabel(code: string | null | undefined): string {
  if (!code) return ''
  return REASON_LABEL[code] ?? code.replace(/_/g, ' ').toLowerCase()
}

export const LANGUAGE_LABEL: Record<string, string> = { hi: 'Hindi', en: 'English' }

export function languageLabel(code: string | null | undefined): string {
  return code ? LANGUAGE_LABEL[code] ?? code : '—'
}

export function deliverableLabel(code: string | null | undefined): string {
  return code ? code.replace(/_/g, ' ') : '—'
}
