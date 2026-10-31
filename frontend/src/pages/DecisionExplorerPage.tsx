import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { Badge, Empty, ErrorBox, Spinner } from '../components/ui'
import { useApi } from '../hooks/useApi'
import { useRepo } from '../lib/repoContext'
import { ALT_STATUS, VERIFICATION, decisionBadge } from '../lib/decisionStatus'
import { card, input, muted } from '../lib/ui'
import { listDecisions } from '../services/api'
import type { DecisionListItem } from '../types/decision'

const FILTERS: [string, string, (d: DecisionListItem) => boolean][] = [
  ['all', 'All', () => true],
  ['accepted', 'Accepted', (d) => d.status === 'accepted'],
  ['rejected', 'Rejected', (d) => d.status === 'rejected' || d.alternatives.some((a) => a.status === 'rejected')],
  ['proposed', 'Proposed', (d) => d.alternatives.some((a) => a.status === 'proposed')],
  ['unresolved', 'Unresolved', (d) => d.status === 'unresolved'],
  ['superseded', 'Superseded', (d) => d.status === 'superseded'],
]

export function DecisionExplorerPage() {
  const { repo } = useRepo()
  const { data, error, loading, reload } = useApi((s) => listDecisions(repo.id, s), [repo.id])
  const [filter, setFilter] = useState('all')
  const [query, setQuery] = useState('')

  const shown = useMemo(() => {
    const test = FILTERS.find((f) => f[0] === filter)![2]
    const q = query.trim().toLowerCase()
    return (data ?? []).filter((d) => test(d) && (!q || `${d.topic} ${d.decision ?? ''} ${d.alternatives.map((a) => a.name).join(' ')}`.toLowerCase().includes(q)))
  }, [data, filter, query])

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <div role="tablist" className="flex flex-wrap gap-1 rounded-lg border border-zinc-200 p-1 dark:border-zinc-800">
          {FILTERS.map(([key, label]) => {
            const n = (data ?? []).filter(FILTERS.find((f) => f[0] === key)![2]).length
            return (
              <button key={key} role="tab" aria-selected={filter === key} onClick={() => setFilter(key)}
                className={`rounded-md px-2.5 py-1 text-sm ${filter === key ? 'bg-zinc-200 font-medium dark:bg-zinc-800' : muted}`}>
                {label} <span className="tabular-nums opacity-60">{n}</span>
              </button>
            )
          })}
        </div>
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search topics and alternatives"
          className={`${input} sm:ml-auto sm:w-72`} aria-label="Search decisions" />
      </div>

      {loading && <Spinner label="Loading decisions…" />}
      {error && <ErrorBox message={error} onRetry={reload} />}
      {data && data.length === 0 && (
        <Empty title="No decisions recorded yet">
          Decisions appear once extracted candidates pass evidence validation. Repository data is collected, but no
          candidate has been validated for this repository.
        </Empty>
      )}
      {data && data.length > 0 && shown.length === 0 && <Empty title="No decisions match this filter" />}

      <ul className="space-y-3">
        {shown.map((d) => {
          const badge = decisionBadge(d)
          const selected = d.alternatives.find((a) => a.status === 'selected')
          const rejected = d.alternatives.filter((a) => a.status === 'rejected')
          const v = VERIFICATION[d.verification_state]
          return (
            <li key={d.id}>
              <Link to={`${d.id}`} className={`${card} block p-5 hover:border-indigo-400/60`}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <p className="font-medium">{d.topic}</p>
                  <div className="flex flex-wrap gap-1.5">
                    <Badge color={badge.color}>{badge.label}</Badge>
                    {d.conflict_detected && <Badge color="amber">conflicting opinions</Badge>}
                  </div>
                </div>
                <dl className="mt-3 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[9rem_1fr]">
                  <dt className={muted}>Decision</dt>
                  <dd>{d.decision ?? <em className={muted}>none established</em>}</dd>
                  <dt className={muted}>Selected</dt>
                  <dd>{selected?.name ?? '—'}</dd>
                  <dt className={muted}>Rejected</dt>
                  <dd>{rejected.length ? rejected.map((a) => `${a.name}${a.rejection_reason ? ` (${a.rejection_reason})` : ' (reason not recorded)'}`).join(', ') : '—'}</dd>
                  <dt className={muted}>Alternatives</dt>
                  <dd className="flex flex-wrap gap-1">
                    {d.alternatives.length ? d.alternatives.map((a) => (
                      <Badge key={a.name} color={ALT_STATUS[a.status]?.color ?? 'gray'}>{a.name}: {ALT_STATUS[a.status]?.label ?? a.status}</Badge>
                    )) : '—'}
                  </dd>
                  <dt className={muted}>Evidence</dt>
                  <dd>
                    {d.evidence_count} cited source{d.evidence_count === 1 ? '' : 's'} ·{' '}
                    <span>{v?.label ?? d.verification_state}</span>
                  </dd>
                  <dt className={muted}>Human review</dt>
                  <dd>{d.requires_human_review ? 'needed' : d.determination === 'human_confirmed' ? 'confirmed by a reviewer' : 'not required'}</dd>
                </dl>
              </Link>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
