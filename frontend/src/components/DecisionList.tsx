import { useEffect, useState } from 'react'

import { decisionBadge } from '../lib/decisionStatus'
import { listDecisions } from '../services/api'
import type { DecisionSummary } from '../types/decision'
import { DecisionDetail } from './DecisionDetail'

export function DecisionList({ repoId }: { repoId: number }) {
  const [items, setItems] = useState<DecisionSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<number | null>(null)
  const [version, setVersion] = useState(0)

  useEffect(() => {
    const c = new AbortController()
    listDecisions(repoId, c.signal)
      .then((data) => {
        setItems(data)
        setError(null)
      })
      .catch((err: unknown) => !c.signal.aborted && setError(err instanceof Error ? err.message : 'Error'))
    return () => c.abort()
  }, [repoId, version])

  if (error) return <p className="rounded-md bg-rose-50 p-3 text-sm text-rose-800">{error}</p>
  if (!items) return <p className="text-sm text-slate-500">Loading decisions…</p>
  if (items.length === 0)
    return <p className="text-sm text-slate-500">No validated decisions yet. Decision extraction arrives in a later milestone.</p>

  return (
    <ul className="space-y-2">
      {items.map((d) => {
        const badge = decisionBadge(d)
        return (
          <li key={d.id} className="rounded-md border border-slate-200">
            <button
              onClick={() => setOpen(open === d.id ? null : d.id)}
              className="flex w-full flex-wrap items-center justify-between gap-2 px-3 py-2 text-left hover:bg-slate-50"
            >
              <span className="font-medium">{d.topic}</span>
              <span className={`rounded-full px-2 py-0.5 text-xs ${badge.cls}`}>{badge.label}</span>
            </button>
            {open === d.id && (
              <div className="border-t border-slate-200 p-3">
                <DecisionDetail id={d.id} onChanged={() => setVersion((v) => v + 1)} />
              </div>
            )}
          </li>
        )
      })}
    </ul>
  )
}
