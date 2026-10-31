import { Background, Controls, MarkerType, ReactFlow, type Edge, type Node } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'

import type { DecisionGraphData, GraphNode } from '../types/views'

// Columns left to right: who → where it was discussed → the decision → options → implementation → files.
const COLUMN: Record<GraphNode['kind'], number> = {
  contributor: 0, issue: 1, discussion: 1, decision: 2, alternative: 3, pull_request: 4, commit: 4, file: 5,
}
const KIND_STYLE: Record<GraphNode['kind'], string> = {
  decision: '#6366f1', alternative: '#a1a1aa', contributor: '#71717a', issue: '#0ea5e9', discussion: '#0ea5e9',
  pull_request: '#10b981', commit: '#10b981', file: '#a1a1aa',
}
const EDGE_COLOR: Record<string, string> = {
  accepted: '#10b981', implemented: '#10b981', rejected: '#f43f5e', 'argued against': '#f43f5e',
  conflicts_with: '#f43f5e', supersedes: '#a1a1aa',
}

const ROWS = 6

export function DecisionGraph({
  data,
  decisionId,
  showPossible = false,
}: {
  data: DecisionGraphData
  decisionId: number
  showPossible?: boolean
}) {
  const navigate = useNavigate()
  const dark = document.documentElement.classList.contains('dark')

  const { nodes, edges } = useMemo(() => {
    // Possible connections are hidden unless asked for; nodes reachable only through them go too.
    const shownEdges = data.edges.filter((e) => showPossible || e.status === 'verified')
    const linked = new Set(shownEdges.flatMap((e) => [e.source, e.target]))
    const shownNodes = data.nodes.filter((n) => n.id === `decision:${decisionId}` || linked.has(n.id))

    const columnOf = (n: GraphNode) => (n.kind === 'decision' && n.id !== `decision:${decisionId}` ? 6 : COLUMN[n.kind])
    const counts: Record<number, number> = {}
    for (const n of shownNodes) counts[columnOf(n)] = (counts[columnOf(n)] ?? 0) + 1
    // Wrap tall columns into sub-columns of ROWS nodes, and shift later columns right accordingly.
    const width: Record<number, number> = {}
    for (const c of Object.keys(counts).map(Number)) width[c] = Math.ceil(counts[c] / ROWS)
    const xStart: Record<number, number> = {}
    let x = 0
    for (let c = 0; c <= 6; c++) {
      xStart[c] = x
      x += (width[c] ?? 0) * 230
    }
    const seen: Record<number, number> = {}
    const nodes: Node[] = shownNodes.map((n) => {
      const col = columnOf(n)
      const i = (seen[col] = (seen[col] ?? -1) + 1)
      const label = n.kind === 'file' && n.deleted ? `${n.label} (deleted)` : n.label
      return {
        id: n.id,
        position: { x: xStart[col] + Math.floor(i / ROWS) * 230, y: (i % ROWS) * 78 },
        data: { label, node: n },
        style: {
          border: `1px solid ${KIND_STYLE[n.kind]}`,
          borderRadius: 10,
          background: dark ? '#18181b' : '#ffffff',
          color: dark ? '#f4f4f5' : '#18181b',
          fontSize: 12,
          width: 200,
          padding: 8,
          cursor: n.url || n.kind === 'decision' ? 'pointer' : 'default',
          fontWeight: n.id === `decision:${decisionId}` ? 600 : 400,
        },
      }
    })
    const edges: Edge[] = shownEdges.map((e, i) => ({
      id: `e${i}`,
      source: e.source,
      target: e.target,
      label: e.status === 'possible' ? `${e.label} (possible)` : e.label,
      animated: false,
      markerEnd: { type: MarkerType.ArrowClosed },
      style: { stroke: EDGE_COLOR[e.label] ?? '#71717a', strokeDasharray: e.status === 'possible' ? '5 4' : undefined },
      labelStyle: { fontSize: 10, fill: dark ? '#d4d4d8' : '#3f3f46' },
      labelBgStyle: { fill: dark ? '#09090b' : '#fafafa' },
    }))
    return { nodes, edges }
  }, [data, decisionId, dark, showPossible])

  return (
    <div className="h-[520px] overflow-hidden rounded-xl border border-zinc-200 dark:border-zinc-800">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        nodesConnectable={false}
        colorMode={dark ? 'dark' : 'light'}
        onNodeClick={(_, node) => {
          const n = (node.data as { node: GraphNode }).node
          if (n.kind === 'decision') navigate(`../${n.id.split(':')[1]}`, { relative: 'path' })
          else if (n.url) window.open(n.url, '_blank', 'noopener,noreferrer')
        }}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={20} size={1} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  )
}
