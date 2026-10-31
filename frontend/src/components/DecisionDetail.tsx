import { useEffect, useState } from 'react'

import { ALT_STATUS, VERIFICATION, decisionBadge } from '../lib/decisionStatus'
import { getDecision } from '../services/api'
import type { Decision, Evidence } from '../types/decision'
import { DecisionContext } from './DecisionContext'
import { ReviewForm } from './ReviewForm'

function EvidenceItem({ e }: { e: Evidence }) {
  const v = VERIFICATION[e.verification_state] ?? { label: e.verification_state, cls: '' }
  return (
    <li className="rounded-md bg-slate-50 p-2">
      <div className="flex flex-wrap items-center gap-x-2 text-xs">
        <span className="font-medium uppercase text-slate-500">{e.claim_type}</span>
        {e.stance && <span className="text-slate-600">{e.stance}s {e.alternative}</span>}
        <span className={v.cls}>{v.label}</span>
        {!e.is_explicit && <span className="text-amber-700">inferred</span>}
        {e.flags.length > 0 && <span className="text-slate-500">({e.flags.join(', ')})</span>}
      </div>
      <p className="mt-1 text-sm">{e.claim_text}</p>
      {e.quote && <blockquote className="mt-1 border-l-2 border-slate-300 pl-2 text-sm text-slate-600">{e.quote}</blockquote>}
      <p className="mt-1 text-xs text-slate-500">
        {e.html_url ? (
          <a href={e.html_url} target="_blank" rel="noreferrer" className="text-indigo-700 hover:underline">
            {e.author_login ? `@${e.author_login}` : 'source'}
            {e.author_association && e.author_association !== 'NONE' ? ` (${e.author_association.toLowerCase()})` : ''} on GitHub
          </a>
        ) : (
          <span className="text-rose-700">cited {e.source_id}: no such source in this repository</span>
        )}
      </p>
    </li>
  )
}

export function DecisionDetail({ id, onChanged }: { id: number; onChanged: () => void }) {
  const [d, setD] = useState<Decision | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const c = new AbortController()
    getDecision(id, c.signal)
      .then(setD)
      .catch((err: unknown) => !c.signal.aborted && setError(err instanceof Error ? err.message : 'Error'))
    return () => c.abort()
  }, [id])

  if (error) return <p className="rounded-md bg-rose-50 p-3 text-sm text-rose-800">{error}</p>
  if (!d) return <p className="text-sm text-slate-500">Loading decision…</p>

  const badge = decisionBadge(d)
  const positions = d.evidence.filter((e) => e.claim_type === 'position')
  const other = d.evidence.filter((e) => e.claim_type !== 'position')

  return (
    <div className="space-y-4">
      <div>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${badge.cls}`}>{badge.label}</span>
        {d.conflict_detected && (
          <span className="ml-2 rounded-full bg-orange-100 px-2.5 py-0.5 text-xs text-orange-900">conflicting opinions</span>
        )}
        <h3 className="mt-2 text-lg font-semibold">{d.topic}</h3>
        {d.problem && <p className="text-sm text-slate-600">{d.problem}</p>}
        <p className="mt-1 text-sm">
          Decision:{' '}
          {d.decision ? <strong>{d.decision}</strong> : <em className="text-slate-500">none established</em>}
        </p>
      </div>

      {d.alternatives.length > 0 && (
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-slate-500">
            <tr>
              <th>Alternative</th>
              <th>Status</th>
              <th>Rejection reason</th>
            </tr>
          </thead>
          <tbody>
            {d.alternatives.map((a) => (
              <tr key={a.name} className="border-t border-slate-100">
                <td className="py-1">{a.name}</td>
                <td>
                  {ALT_STATUS[a.status] ?? a.status}
                  {a.proposed_status !== a.status && (
                    <span className="text-xs text-slate-400"> (extractor said {ALT_STATUS[a.proposed_status]})</span>
                  )}
                </td>
                <td className="text-slate-600">{a.rejection_reason ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {positions.length > 0 && (
        <section>
          <h4 className="mb-1 text-sm font-medium">Positions (all sides kept)</h4>
          <ul className="space-y-2">{positions.map((e, i) => <EvidenceItem key={i} e={e} />)}</ul>
        </section>
      )}
      {other.length > 0 && (
        <section>
          <h4 className="mb-1 text-sm font-medium">Evidence</h4>
          <ul className="space-y-2">{other.map((e, i) => <EvidenceItem key={i} e={e} />)}</ul>
        </section>
      )}
      <DecisionContext decisionId={d.id} />
      {d.validation_notes.length > 0 && (
        <section>
          <h4 className="mb-1 text-sm font-medium">Validation notes</h4>
          <ul className="list-disc pl-5 text-sm text-slate-600">{d.validation_notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
        </section>
      )}
      {d.reviews.length > 0 && (
        <section>
          <h4 className="mb-1 text-sm font-medium">Reviews</h4>
          <ul className="space-y-1 text-sm">
            {d.reviews.map((r, i) => (
              <li key={i}>
                @{r.reviewer_login} ({r.reviewer_permission}) set <strong>{r.outcome_status}</strong>
                {r.selected_alternative && <> selecting {r.selected_alternative}</>} on{' '}
                {new Date(r.created_at).toLocaleString()}: {r.explanation}
              </li>
            ))}
          </ul>
        </section>
      )}
      <section>
        <h4 className="mb-1 text-sm font-medium">History</h4>
        <ol className="text-xs text-slate-600">
          {d.history.map((h, i) => (
            <li key={i}>
              {new Date(h.created_at).toLocaleString()}: {h.event} by {h.actor}
              {typeof h.snapshot.status === 'string' && <> (was {h.snapshot.status})</>}
            </li>
          ))}
        </ol>
      </section>
      {d.status !== 'superseded' && (
        <ReviewForm
          decision={d}
          onReviewed={(nd) => {
            setD(nd)
            onChanged()
          }}
        />
      )}
    </div>
  )
}
