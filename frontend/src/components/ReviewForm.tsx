import { useState, type FormEvent } from 'react'

import { reviewDecision } from '../services/api'
import type { Decision, ReviewRequest } from '../types/decision'

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
    <form onSubmit={submit} className="space-y-3 rounded-md border border-slate-200 p-4 text-sm">
      <h4 className="font-medium">Human review</h4>
      <p className="text-slate-500">
        Only someone with write access to this repository can record an outcome. GitHub verifies your identity from your
        token; DeciTrace never stores it.
      </p>
      <label className="block">
        Outcome
        <select
          value={outcome}
          onChange={(e) => setOutcome(e.target.value as ReviewRequest['outcome_status'])}
          className="mt-1 block w-full rounded-md border border-slate-300 px-2 py-1.5"
        >
          <option value="unresolved">Keep unresolved</option>
          <option value="accepted">Accepted</option>
          <option value="rejected">Rejected</option>
          <option value="deferred">Deferred</option>
        </select>
      </label>
      {outcome !== 'unresolved' && decision.alternatives.length > 0 && (
        <>
          <label className="block">
            Selected alternative
            <select
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
              className="mt-1 block w-full rounded-md border border-slate-300 px-2 py-1.5"
            >
              <option value="">(none)</option>
              {decision.alternatives.map((a) => (
                <option key={a.name}>{a.name}</option>
              ))}
            </select>
          </label>
          <fieldset>
            <legend>Explicitly rejected (others become "considered, not selected")</legend>
            {decision.alternatives
              .filter((a) => a.name !== selected)
              .map((a) => (
                <div key={a.name} className="mt-1 flex items-center gap-2">
                  <input type="checkbox" checked={a.name in rejected} onChange={() => toggle(a.name)} id={`rej-${a.name}`} />
                  <label htmlFor={`rej-${a.name}`}>{a.name}</label>
                  {a.name in rejected && (
                    <input
                      placeholder="reason (optional)"
                      value={rejected[a.name] ?? ''}
                      onChange={(e) => setRejected((r) => ({ ...r, [a.name]: e.target.value }))}
                      className="flex-1 rounded-md border border-slate-300 px-2 py-1"
                    />
                  )}
                </div>
              ))}
          </fieldset>
        </>
      )}
      <label className="block">
        Explanation (required)
        <textarea
          value={explanation}
          onChange={(e) => setExplanation(e.target.value)}
          minLength={10}
          required
          rows={3}
          className="mt-1 block w-full rounded-md border border-slate-300 px-2 py-1.5"
        />
      </label>
      <label className="block">
        Your GitHub token
        <input
          type="password"
          autoComplete="off"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          required
          className="mt-1 block w-full rounded-md border border-slate-300 px-2 py-1.5"
        />
      </label>
      {error && (
        <p role="alert" className="rounded-md bg-rose-50 p-2 text-rose-800">
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={busy}
        className="rounded-md bg-indigo-600 px-3 py-1.5 font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
      >
        {busy ? 'Verifying…' : 'Record review'}
      </button>
    </form>
  )
}
