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
  /** How the last finished sync ran: with a GitHub token (large sample) or without (small sample). */
  sync: { authenticated: boolean | null; limits: Record<string, number> | null; finished_at: string | null }
  /** The threads with the most discussion that DeciTrace collected, with whether extraction has read them. */
  top_threads: { kind: string; number: number; title: string | null; url: string; comments: number; analysed: boolean }[]
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

export interface ExtractionJob {
  id: number
  status: 'queued' | 'running' | 'completed' | 'partial' | 'failed'
  model: string
  threads_total: number
  threads_done: number
  candidates: number
  created: number
  merged: number
  refused: number
  errors: { thread: string; error: string; message: string }[]
  created_at: string
  finished_at: string | null
}

export interface ImpactFinding {
  decision_id: number
  topic: string
  decision: string | null
  status: 'accepted' | 'rejected' | 'unresolved' | 'deferred' | 'superseded'
  determination: 'explicit' | 'inferred' | 'human_confirmed' | 'unresolved'
  severity: 'potential_conflict' | 'related'
  headline: string
  triggers: { signal: string; detail: string; file: string; lines: string[] }[]
  triggered_by_files: string[]
  supporting_sources: { url: string; author: string | null; claim_type: string; quote: string; verification_state: string }[]
}

export interface ImpactReport {
  repository_id: number
  pull_request: { number: number; title: string; url: string; state: string; merged: boolean; author: string | null }
  changed_files: { filename: string; status: string; previous_filename: string | null; additions: number; deletions: number }[]
  findings: ImpactFinding[]
  note: string
  decisions_checked: number
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
