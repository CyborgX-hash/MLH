import type { DecisionSummary } from '../types/decision'

// Only an explicit statement or a human confirmation is ever shown in green.
// Inferred and unresolved decisions are visibly NOT approved.
export function decisionBadge(d: Pick<DecisionSummary, 'status' | 'determination'>): { label: string; cls: string } {
  if (d.status === 'superseded') return { label: 'Superseded', cls: 'bg-slate-200 text-slate-700' }
  if (d.status === 'unresolved') return { label: 'Unresolved: needs human review', cls: 'bg-amber-100 text-amber-900' }
  if (d.determination === 'inferred')
    return { label: `Inferred ${d.status}: not explicitly approved`, cls: 'bg-amber-100 text-amber-900' }
  const how = d.determination === 'human_confirmed' ? 'confirmed by reviewer' : 'explicit in sources'
  if (d.status === 'accepted') return { label: `Accepted (${how})`, cls: 'bg-emerald-100 text-emerald-800' }
  if (d.status === 'rejected') return { label: `Rejected (${how})`, cls: 'bg-rose-100 text-rose-800' }
  return { label: `Deferred (${how})`, cls: 'bg-slate-100 text-slate-700' }
}

export const VERIFICATION: Record<string, { label: string; cls: string }> = {
  verified: { label: 'verified', cls: 'text-emerald-700' },
  partially_verified: { label: 'partially verified', cls: 'text-amber-700' },
  unsupported: { label: 'unsupported', cls: 'text-rose-700' },
  needs_human_review: { label: 'needs human review', cls: 'text-amber-700' },
}

export const ALT_STATUS: Record<string, string> = {
  selected: 'selected',
  rejected: 'rejected',
  considered_not_selected: 'considered, not selected',
  proposed: 'proposed',
  deferred: 'deferred',
}
