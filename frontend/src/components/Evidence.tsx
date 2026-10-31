import { VERIFICATION } from '../lib/decisionStatus'
import { muted } from '../lib/ui'
import type { Evidence } from '../types/decision'
import { Badge, ExternalLink } from './ui'

const CLAIM: Record<string, string> = {
  resolution: 'Resolution',
  reason: 'Reasoning',
  alternative: 'Proposal',
  rejection: 'Objection',
  position: 'Position',
}

export function EvidenceItem({ e }: { e: Evidence }) {
  const v = VERIFICATION[e.verification_state] ?? { label: e.verification_state, color: 'gray' as const }
  return (
    <li className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-800">
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        <Badge>{CLAIM[e.claim_type] ?? e.claim_type}</Badge>
        {e.stance && <Badge color={e.stance === 'oppose' ? 'red' : e.stance === 'support' ? 'blue' : 'gray'}>{e.stance}s {e.alternative}</Badge>}
        <Badge color={v.color}>{v.label}</Badge>
        {!e.is_explicit && <Badge color="amber">inferred</Badge>}
        {e.flags.length > 0 && <span className={muted}>{e.flags.join(', ').replaceAll('_', ' ')}</span>}
      </div>
      <p className="mt-1.5 text-sm">{e.claim_text}</p>
      {e.quote && <blockquote className={`mt-1.5 border-l-2 border-zinc-300 pl-3 text-sm dark:border-zinc-700 ${muted}`}>{e.quote}</blockquote>}
      <p className={`mt-1.5 text-xs ${muted}`}>
        {e.html_url ? (
          <ExternalLink href={e.html_url}>
            {e.author_login ? `@${e.author_login}` : 'source'}
            {e.author_association && e.author_association !== 'NONE' ? ` (${e.author_association.toLowerCase()})` : ''} on GitHub
          </ExternalLink>
        ) : (
          <span className="text-rose-600 dark:text-rose-400">cited {e.source_id}: no such source in this repository</span>
        )}
      </p>
    </li>
  )
}
