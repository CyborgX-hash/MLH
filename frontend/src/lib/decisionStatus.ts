import type { DecisionSummary } from '../types/decision'
import type { tone } from './ui'

type Tone = keyof typeof tone

// Only an explicit statement or a human confirmation is ever shown in green.
// Inferred and unresolved decisions are visibly NOT approved.
export function decisionBadge(d: Pick<DecisionSummary, 'status' | 'determination'>): { label: string; color: Tone } {
  if (d.status === 'superseded') return { label: 'Superseded', color: 'gray' }
  if (d.status === 'unresolved') return { label: 'Unresolved: needs human review', color: 'amber' }
  if (d.determination === 'inferred') return { label: `Inferred ${d.status}: not explicitly approved`, color: 'amber' }
  const how = d.determination === 'human_confirmed' ? 'confirmed by reviewer' : 'explicit in sources'
  if (d.status === 'accepted') return { label: `Accepted (${how})`, color: 'green' }
  if (d.status === 'rejected') return { label: `Rejected (${how})`, color: 'red' }
  return { label: `Deferred (${how})`, color: 'gray' }
}

export const VERIFICATION: Record<string, { label: string; color: Tone }> = {
  verified: { label: 'verified', color: 'green' },
  partially_verified: { label: 'partially verified', color: 'amber' },
  unsupported: { label: 'unsupported', color: 'red' },
  needs_human_review: { label: 'needs human review', color: 'amber' },
}

export const ALT_STATUS: Record<string, { label: string; color: Tone }> = {
  selected: { label: 'selected', color: 'green' },
  rejected: { label: 'rejected', color: 'red' },
  considered_not_selected: { label: 'considered, not selected', color: 'gray' },
  proposed: { label: 'proposed', color: 'blue' },
  deferred: { label: 'deferred', color: 'gray' },
}

export const SOURCE_LABEL: Record<string, string> = {
  issue: 'Issue',
  pull_request: 'PR',
  discussion: 'Discussion',
  commit: 'Commit',
  comment: 'Comment',
  decision: 'Decision',
  file: 'File',
}
