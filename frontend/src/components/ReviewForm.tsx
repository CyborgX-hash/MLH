import { useState, type FormEvent } from 'react'

import { btnPrimary, input, muted } from '../lib/ui'
import { reviewDecision } from '../services/api'
import type { Decision, ReviewRequest } from '../types/decision'
import { ErrorBox } from './ui'

export function ReviewForm({ decision, onReviewed }: { decision: Decision; onReviewed: (d: Decision) => void }) {
  const [outcome, setOutcome] = useState<ReviewRequest['outcome_status']>('unresolved')
  const [selected, setSelected] = useState('')
  const [rejected, setRejected] = useState<Record<string, string | null>>({})
  const [explanation, setExplanation] = useState('')
  const [token, setToken] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const body: ReviewRequest = {
        outcome_status: outcome,
        selected_alternative: outcome === 'unresolved' ? null : selected || null,
        rejected_alternatives:
          outcome === 'unresolved' ? [] : Object.entries(rejected).map(([name, reason]) => ({ name, reason: reason || null })),
        explanation,
      }
      onReviewed(await reviewDecision(decision.id, body, token))
      setToken('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Review failed.')
    } finally {
      setBusy(false)
    }
  }

  const toggle = (name: string) =>
    setRejected((r) => {
      const next = { ...r }
      if (name in next) delete next[name]
      else next[name] = null
      return next
    })

  return (
    <form onSubmit={submit} className="space-y-4 text-sm">
      <p className={muted}>
        Only someone with write access to this repository can record an outcome. GitHub confirms who you are from your
        own token; DeciTrace uses it for two checks and never stores it.
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="font-medium">Outcome</span>
          <select value={outcome} onChange={(e) => setOutcome(e.target.value as ReviewRequest['outcome_status'])} className={`${input} mt-1`}>
            <option value="unresolved">Keep unresolved</option>
            <option value="accepted">Accepted</option>
            <option value="rejected">Rejected</option>
            <option value="deferred">Deferred</option>
          </select>
        </label>
        {outcome !== 'unresolved' && decision.alternatives.length > 0 && (
          <label className="block">
            <span className="font-medium">Selected alternative</span>
            <select value={selected} onChange={(e) => setSelected(e.target.value)} className={`${input} mt-1`}>
              <option value="">(none)</option>
              {decision.alternatives.map((a) => <option key={a.name}>{a.name}</option>)}
            </select>
          </label>
        )}
      </div>
      {outcome !== 'unresolved' && decision.alternatives.length > 0 && (
        <fieldset>
          <legend className="font-medium">Explicitly rejected</legend>
          <p className={`text-xs ${muted}`}>Alternatives left unticked are recorded as "considered, not selected".</p>
          {decision.alternatives.filter((a) => a.name !== selected).map((a) => (
            <div key={a.name} className="mt-2 flex items-center gap-2">
              <input type="checkbox" checked={a.name in rejected} onChange={() => toggle(a.name)} id={`rej-${decision.id}-${a.name}`} />
              <label htmlFor={`rej-${decision.id}-${a.name}`}>{a.name}</label>
              {a.name in rejected && (
                <input placeholder="reason (optional)" value={rejected[a.name] ?? ''}
                  onChange={(e) => setRejected((r) => ({ ...r, [a.name]: e.target.value }))} className={`${input} flex-1 py-1`} />
              )}
            </div>
          ))}
        </fieldset>
      )}
      <label className="block">
        <span className="font-medium">Explanation (required)</span>
        <textarea value={explanation} onChange={(e) => setExplanation(e.target.value)} minLength={10} required rows={3} className={`${input} mt-1`} />
      </label>
      <label className="block">
        <span className="font-medium">Your GitHub token</span>
        <input type="password" autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} required className={`${input} mt-1`} />
      </label>
      {error && <ErrorBox message={error} />}
      <button type="submit" disabled={busy} className={btnPrimary}>{busy ? 'Verifying with GitHub…' : 'Record review'}</button>
    </form>
  )
}
