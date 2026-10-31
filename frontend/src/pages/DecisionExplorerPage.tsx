import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { Badge, Empty, ErrorBox, ExternalLink, Spinner } from '../components/ui'
import { useApi } from '../hooks/useApi'
import { decisionBadge, SOURCE_LABEL } from '../lib/decisionStatus'
import { evidenceSentence, nextStep, optionPhrase, statusSentence } from '../lib/explain'
import { useRepo } from '../lib/repoContext'
import { card, input, link, muted } from '../lib/ui'
import { listDecisions } from '../services/api'
import type { DecisionListItem, SourceThread } from '../types/decision'

const FILTERS: [string, string, string, (d: DecisionListItem) => boolean][] = [
  ['all', 'All', 'Every recorded decision', () => true],
  ['accepted', 'Accepted', 'An outcome was decided', (d) => d.status === 'accepted'],
  ['rejected', 'Rejected', 'A proposal was turned down, or an option was explicitly rejected', (d) => d.status === 'rejected' || d.alternatives.some((a) => a.status === 'rejected')],
  ['proposed', 'Proposed', 'Has options that were suggested but not decided', (d) => d.alternatives.some((a) => a.status === 'proposed')],
  ['unresolved', 'Unresolved', 'No final outcome yet', (d) => d.status === 'unresolved'],
  ['superseded', 'Superseded', 'Replaced by a later decision', (d) => d.status === 'superseded'],
]

const OPTION_COLOR = { selected: 'green', rejected: 'red', considered_not_selected: 'gray', deferred: 'gray', proposed: 'blue' } as const

function threadLabel(s: SourceThread) {
  return `${SOURCE_LABEL[s.kind] ?? s.kind}${s.number ? ` #${s.number}` : ''}`
}

function DecisionCard({ d }: { d: DecisionListItem }) {
  const badge = decisionBadge(d)
  const step = nextStep(d)
  const maintainers = d.participants.filter((p) => p.association && ['OWNER', 'MEMBER', 'COLLABORATOR'].includes(p.association))
  return (
    <article className={`${card} p-5`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <Link to={`${d.id}`} className="text-lg font-medium hover:underline">{d.topic}</Link>
        <div className="flex flex-wrap gap-1.5">
          <Badge color={badge.color}>{badge.label}</Badge>
          {d.conflict_detected && <Badge color="amber">people disagreed</Badge>}
        </div>
      </div>

      <p className="mt-2">{statusSentence(d)}</p>
      {d.problem && <p className={`mt-1 text-sm ${muted}`}><span className="font-medium">Question:</span> {d.problem}</p>}

      <dl className="mt-4 grid gap-x-6 gap-y-3 text-sm sm:grid-cols-[9rem_1fr]">
        <dt className={muted}>Discussed in</dt>
        <dd className="space-y-0.5">
          {d.sources.length === 0 && <span className={muted}>not linked to a thread</span>}
          {d.sources.map((s) => (
            <div key={`${s.kind}${s.number}`}>
              {s.url ? <ExternalLink href={s.url}>{threadLabel(s)}</ExternalLink> : threadLabel(s)}
              {s.title && <span className={muted}> · {s.title}</span>}
            </div>
          ))}
        </dd>

        <dt className={muted}>Options discussed</dt>
        <dd>
          {d.alternatives.length === 0 ? <span className={muted}>none recorded</span> : (
            <ul className="space-y-1">
              {d.alternatives.map((a) => (
                <li key={a.name} className="flex flex-wrap items-baseline gap-2">
                  <span>{a.name}</span>
                  <Badge color={OPTION_COLOR[a.status as keyof typeof OPTION_COLOR] ?? 'gray'}>{optionPhrase(a)}</Badge>
                </li>
              ))}
            </ul>
          )}
        </dd>

        <dt className={muted}>People</dt>
        <dd>
          {d.participants.length === 0 ? <span className={muted}>—</span> : d.participants.map((p, i) => (
            <span key={p.login}>
              {i > 0 && ', '}@{p.login}
              {p.association && p.association !== 'NONE' && <span className={muted}> ({p.association.toLowerCase()})</span>}
            </span>
          ))}
          {d.participants.length > 0 && maintainers.length === 0 && <span className={muted}> · no maintainer took part</span>}
        </dd>

        <dt className={muted}>Evidence</dt>
        <dd>{evidenceSentence(d.evidence_count, d.verified_evidence)}</dd>
      </dl>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 text-sm">
        {step ? <span className="text-amber-700 dark:text-amber-300">{step}</span> : <span />}
        <Link to={`${d.id}`} className={link}>Open full history →</Link>
      </div>
    </article>
  )
}

export function DecisionExplorerPage() {
  const { repo } = useRepo()
  const { data, error, loading, reload } = useApi((s) => listDecisions(repo.id, s), [repo.id])
  const [filter, setFilter] = useState('all')
  const [query, setQuery] = useState('')

  const shown = useMemo(() => {
    const test = FILTERS.find((f) => f[0] === filter)![3]
    const q = query.trim().toLowerCase()
    return (data ?? []).filter((d) => test(d) && (!q || `${d.topic} ${d.problem ?? ''} ${d.decision ?? ''} ${d.alternatives.map((a) => a.name).join(' ')}`.toLowerCase().includes(q)))
  }, [data, filter, query])

  return (
    <div className="space-y-5">
      <p className={`max-w-3xl text-sm ${muted}`}>
        Each decision was found by an AI model in this repository's discussions and kept only where its quotes match the
        real comments. DeciTrace never decides on its own: when nobody with authority stated an outcome, the decision stays
        unresolved until a maintainer confirms it.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <div role="tablist" className="flex flex-wrap gap-1 rounded-lg border border-zinc-200 p-1 dark:border-zinc-800">
          {FILTERS.map(([key, label, hint, test]) => (
            <button key={key} role="tab" title={hint} aria-selected={filter === key} onClick={() => setFilter(key)}
              className={`rounded-md px-2.5 py-1 text-sm ${filter === key ? 'bg-zinc-200 font-medium dark:bg-zinc-800' : muted}`}>
              {label} <span className="tabular-nums opacity-60">{(data ?? []).filter(test).length}</span>
            </button>
          ))}
        </div>
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search topics and options"
          className={`${input} sm:ml-auto sm:w-72`} aria-label="Search decisions" />
      </div>

      {loading && <Spinner label="Loading decisions…" />}
      {error && <ErrorBox message={error} onRetry={reload} />}
      {data && data.length === 0 && (
        <Empty title="No decisions recorded yet">
          Press <strong>Extract decisions</strong> on the dashboard. The model reads the most-discussed threads, and only
          candidates whose quotes match real comments are recorded.
        </Empty>
      )}
      {data && data.length > 0 && shown.length === 0 && <Empty title="No decisions match this filter" />}

      <ul className="space-y-3">{shown.map((d) => <li key={d.id}><DecisionCard d={d} /></li>)}</ul>
    </div>
  )
}
