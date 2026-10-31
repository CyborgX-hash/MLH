export interface Overview {
  counts: {
    issues: number
    pull_requests: number
    discussions: number
    discussions_collected: number
    comments: number
    commits: number
    source_files: number
    decisions: number
    accepted: number
    rejected: number
    unresolved: number
    deferred: number
    superseded: number
    needs_review: number
    rejected_alternatives: number
  }
  recent_activity: { decision_id: number; topic: string; event: string; actor: string; at: string }[]
}

export interface TimelineEvent {
  type: 'proposal' | 'argument' | 'rejection' | 'approval' | 'implementation' | 'commit' | 'human_review' | 'superseded'
  label: string
  at: string | null
  url: string | null
  author: string | null
  quote: string | null
  verified: boolean
  source: string
}

export interface GraphNode {
  id: string
  kind: 'decision' | 'alternative' | 'contributor' | 'issue' | 'pull_request' | 'discussion' | 'commit' | 'file'
  label: string
  url: string | null
  title?: string | null
  status?: string | null
  determination?: string | null
  deleted?: boolean | null
  original_path?: string | null
}

export interface GraphEdge {
  source: string
  target: string
  label: string
  status: 'verified' | 'possible'
}

export interface DecisionGraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface Citation {
  id: string
  source_type: string
  source_number: number | null
  url: string | null
  title: string
  evidence: string
  author: string | null
}

export interface AskResponse {
  answer: string
  citations: Citation[]
  confidence: 'supported' | 'partial' | 'insufficient'
  insufficient_evidence: boolean
  conflicts: { decision_id: number; topic: string; alternatives: string[] }[]
  decisions: { id: number; topic: string; status: string; determination: string; implementation: string }[]
  warnings: string[]
  retrieval: { mode?: string; hits?: number }
  model: string | null
}
