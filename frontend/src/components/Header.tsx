import type { Bootstrap, CampaignSummary, Health } from '../api/types'
import { formatIst } from '../lib/format'

export function Header({ campaigns, campaignId, onCampaign, onNewSession, newSessionBusy, health, bootstrap }: {
  campaigns: CampaignSummary[]
  campaignId: string | null
  onCampaign: (id: string) => void
  onNewSession: () => void
  newSessionBusy: boolean
  health: Health | undefined
  bootstrap: Bootstrap | undefined
}) {
  const graphOk = !!health?.graph.reachable && !!health?.graph.seeded
  const modelOk = !!health?.model.installed && !!health?.model.reachable
  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true">C</span>
        <div>
          <h1>Campaign Context Agent</h1>
          <small>Creator replacement · local</small>
        </div>
      </div>
      <label className="field-inline">
        Campaign
        <select className="select" value={campaignId ?? ''} onChange={(e) => onCampaign(e.target.value)}>
          {campaigns.map((c) => <option key={c.id} value={c.id}>{c.title} · {c.client_brand_name}</option>)}
        </select>
      </label>
      <button type="button" className="btn" onClick={onNewSession} disabled={newSessionBusy}>New session</button>
      <div className="topbar-spacer" />
      <div className="status-pills" aria-label="Local services">
        <span className={`pill ${health ? (graphOk ? 'ok' : 'bad') : ''}`}>
          <span className="dot" aria-hidden="true" />FalkorDB {health ? (graphOk ? 'connected' : health.graph.reachable ? 'not seeded' : 'down') : 'checking…'}
        </span>
        <span className={`pill ${health ? (modelOk ? 'ok' : 'bad') : ''}`} title={health ? `${health.model.tag}: ${health.model.detail}` : undefined}>
          <span className="dot" aria-hidden="true" />Model {health ? (modelOk ? health.model.tag.split('-')[0] : 'unavailable') : 'checking…'}
        </span>
      </div>
      <div className="stamp" role="note" aria-label="Synthetic demo data and the demo as-of time">
        <span className="stamp-title">Synthetic demo data</span>
        <span className="stamp-date">As of {bootstrap ? formatIst(bootstrap.as_of_ms) : '…'}</span>
        <span className="stamp-meta">{bootstrap?.clock ?? ''}{bootstrap?.context_revision ? ` · revision ${bootstrap.context_revision}` : ''}</span>
      </div>
    </header>
  )
}
