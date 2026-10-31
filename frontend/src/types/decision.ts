export type DecisionStatus = 'accepted' | 'rejected' | 'unresolved' | 'deferred' | 'superseded'
export type Determination = 'explicit' | 'inferred' | 'human_confirmed' | 'unresolved'

export interface DecisionSummary {
  id: number
  repository_id: number
  topic: string
  problem: string | null
  decision: string | null
  status: DecisionStatus
  determination: Determination
  verification_state: string
  conflict_detected: boolean
  requires_human_review: boolean
  superseded_by_id: number | null
  created_by: string
  created_at: string
  updated_at: string
}

export interface DecisionListItem extends DecisionSummary {
  alternatives: Alternative[]
  evidence_count: number
}

export interface Evidence {
  claim_type: string
  claim_text: string
  alternative: string | null
  stance: string | null
  is_explicit: boolean
  source_id: string
  source_kind: string | null
  html_url: string | null
  author_login: string | null
  author_association: string | null
  quote: string | null
  verification_state: string
  flags: string[]
}

export interface Alternative {
  name: string
  status: string
  proposed_status: string
  rejection_reason: string | null
  verification_state: string
}

export interface Review {
  reviewer_login: string
  reviewer_permission: string
  action: string
  outcome_status: string
  selected_alternative: string | null
  explanation: string
  created_at: string
}

export interface HistoryEvent {
  event: string
  actor: string
  snapshot: Record<string, unknown>
  details: Record<string, unknown>
  created_at: string
}

export interface Decision extends DecisionSummary {
  validation_notes: string[]
  alternatives: Alternative[]
  evidence: Evidence[]
  reviews: Review[]
  history: HistoryEvent[]
}

export interface ReviewRequest {
  outcome_status: 'accepted' | 'rejected' | 'deferred' | 'unresolved'
  selected_alternative?: string | null
  decision?: string | null
  rejected_alternatives: { name: string; reason: string | null }[]
  explanation: string
}
