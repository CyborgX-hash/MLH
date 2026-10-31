// Plain-language wording for decisions, so a reader never has to decode status codes.
import type { Alternative, DecisionSummary } from '../types/decision'

export function statusSentence(d: Pick<DecisionSummary, 'status' | 'determination' | 'conflict_detected' | 'decision'>): string {
  if (d.status === 'superseded') return 'This decision was later replaced by a newer one.'
  if (d.status === 'unresolved') {
    return d.conflict_detected
      ? 'People disagreed and no maintainer has confirmed an outcome yet.'
      : 'Options were discussed, but nobody with authority stated a final choice yet.'
  }
  const what = d.decision ? `“${d.decision}”` : 'An outcome'
  if (d.determination === 'inferred') return `${what} was implemented in a merged pull request, but nobody explicitly approved it in the discussion.`
  if (d.determination === 'human_confirmed') return `${what} was confirmed by a maintainer in DeciTrace.`
  const verb = d.status === 'accepted' ? 'was decided' : d.status === 'rejected' ? 'was rejected' : 'was deferred'
  return `${what} ${verb}, stated by a maintainer in the discussion.`
}

export function nextStep(d: Pick<DecisionSummary, 'requires_human_review' | 'status'>): string | null {
  if (d.status === 'superseded') return null
  return d.requires_human_review ? 'A maintainer should confirm the outcome in Conflict review.' : null
}

export function optionPhrase(a: Alternative): string {
  switch (a.status) {
    case 'selected':
      return 'chosen'
    case 'rejected':
      return a.rejection_reason ? `rejected: ${a.rejection_reason}` : 'rejected (reason not recorded)'
    case 'considered_not_selected':
      return 'considered, not chosen'
    case 'deferred':
      return 'postponed'
    default:
      return 'suggested, no decision yet'
  }
}

export function evidenceSentence(total: number, verified: number): string {
  if (total === 0) return 'No supporting comments.'
  const v = verified === total ? 'all checked word for word' : verified > 0 ? `${verified} checked word for word, the rest loosely matched` : 'loosely matched, not word for word'
  return `Backed by ${total} quote${total === 1 ? '' : 's'} from the discussion (${v}).`
}
