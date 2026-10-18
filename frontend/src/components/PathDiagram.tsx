import type { EvidencePath } from '../api/types'

const NODE_W = 236
const NODE_H = 42
const GAP = 46
const LEFT = 8

/** Vertical chain-of-custody drawing of one graph path. Every relationship is labelled; the same
 *  path is also given as an ordered list so the picture is never the only way to read it. */
export function PathDiagram({ path, hot }: { path: EvidencePath; hot: boolean }) {
  const height = path.nodes.length * NODE_H + (path.nodes.length - 1) * GAP + 4
  const width = NODE_W + 220
  const y = (i: number) => 2 + i * (NODE_H + GAP)
  return (
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Graph path: ${path.nodes.map((n) => n.name).join(', then ')}`}>
      {path.edges.map((e, i) => {
        const top = y(i) + NODE_H
        const bottom = y(i + 1)
        const mid = (top + bottom) / 2
        const x = LEFT + NODE_W / 2
        const undirected = e.type === 'COMPETES_WITH'
        return (
          <g key={`${e.from}-${e.type}-${e.to}`} className={`svg-edge ${hot ? 'hot' : ''}`}>
            <line x1={x} y1={top} x2={x} y2={bottom - (undirected ? 0 : 6)} />
            {!undirected ? <path d={`M ${x - 5} ${bottom - 8} L ${x} ${bottom - 1} L ${x + 5} ${bottom - 8}`} fill="none" stroke="currentColor" className={hot ? 'hot' : ''} style={{ stroke: hot ? 'var(--accent)' : 'var(--rule-strong)', strokeWidth: 1.5 }} /> : null}
            <text x={x + 12} y={mid + 3.5}>{e.type}{undirected ? ' (either direction)' : ''}</text>
          </g>
        )
      })}
      {path.nodes.map((n, i) => (
        <g key={n.id} className={`svg-node ${hot && (i === 0 || i === path.nodes.length - 1) ? 'hot' : ''}`}>
          <rect x={LEFT} y={y(i)} width={NODE_W} height={NODE_H} rx={7} />
          <text className="kind" x={LEFT + 10} y={y(i) + 15}>{n.label}</text>
          <text className="label" x={LEFT + 10} y={y(i) + 32}>{n.name.length > 30 ? n.name.slice(0, 29) + '…' : n.name}</text>
        </g>
      ))}
    </svg>
  )
}

export function PathList({ path, onSource }: { path: EvidencePath; onSource: (id: string) => void }) {
  const name = (id: string) => path.nodes.find((n) => n.id === id)?.name ?? id
  return (
    <ol>
      {path.edges.map((e) => (
        <li key={`${e.from}-${e.type}-${e.to}`}>
          {name(e.from)} <strong>{e.type}</strong> {name(e.to)}
          {e.source_ids.length > 0 ? <> · source {e.source_ids.map((s) => (
            <button key={s} type="button" className="btn link" style={{ fontSize: 12 }} onClick={() => onSource(s)}>{s}</button>
          ))}</> : null}
        </li>
      ))}
    </ol>
  )
}
