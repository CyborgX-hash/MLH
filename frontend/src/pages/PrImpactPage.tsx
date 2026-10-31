import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { Badge, Empty, ErrorBox, ExternalLink, Spinner } from '../components/ui'
import { decisionBadge } from '../lib/decisionStatus'
import { useRepo } from '../lib/repoContext'
import { btnPrimary, card, input, muted } from '../lib/ui'
import { analyzePullRequest } from '../services/api'
import type { ImpactReport } from '../types/views'

const SIGNAL: Record<string, string> = {
  deletes_implementation: 'Deletes implementing file',
  removes_decision_code: 'Removes decision-related code',
  introduces_rejected: 'Reintroduces a rejected alternative',
  touches_implementation: 'Changes implementing file',
}

export function PrImpactPage() {
  const { repo } = useRepo()
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [report, setReport] = useState<ImpactReport | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setReport(null)
    try {
      setReport(await analyzePullRequest(url.trim()))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed.')
    } finally {
      setBusy(false)
    }
  }

  const conflicts = report?.findings.filter((f) => f.severity === 'potential_conflict') ?? []
  const related = report?.findings.filter((f) => f.severity === 'related') ?? []

  return (
    <div className="space-y-6">
      <form onSubmit={submit} className={`${card} p-5`}>
        <label htmlFor="pr-url" className="font-medium">Pull request URL</label>
        <p className={`text-sm ${muted}`}>
          Checks a pull request against {repo.full_name}'s recorded decisions. Findings are prompts for reviewers, not
          verdicts: DeciTrace never blocks or rejects a pull request.
        </p>
        <div className="mt-3 flex flex-col gap-2 sm:flex-row">
          <input id="pr-url" value={url} onChange={(e) => setUrl(e.target.value)} className={input}
            placeholder={`https://github.com/${repo.full_name}/pull/123`} disabled={busy} />
          <button type="submit" className={btnPrimary} disabled={busy || !url.trim()}>{busy ? 'Analysing…' : 'Analyse'}</button>
        </div>
      </form>

      {busy && <Spinner label="Fetching changed files and checking historical decisions…" />}
      {error && <ErrorBox message={error} />}

      {report && (
        <div className="space-y-6">
          <div className={`${card} p-5`}>
            <p className="font-medium">
              <ExternalLink href={report.pull_request.url}>#{report.pull_request.number}</ExternalLink> {report.pull_request.title}
            </p>
            <p className={`mt-1 text-sm ${muted}`}>
              {report.pull_request.merged ? 'merged' : report.pull_request.state}
              {report.pull_request.author && <> · by @{report.pull_request.author}</>} · {report.changed_files.length} changed
              file{report.changed_files.length === 1 ? '' : 's'} · {report.decisions_checked} decisions checked
            </p>
            <p className={`mt-3 text-xs ${muted}`}>{report.note}</p>
          </div>

          {report.findings.length === 0 && (
            <Empty title="No historical decisions are linked to these changes">
              None of the changed files implemented a recorded decision, and no rejected alternative reappears. This
              only covers decisions DeciTrace has recorded for this repository.
            </Empty>
          )}

          {[...conflicts, ...related].map((f) => {
            const badge = decisionBadge(f)
            return (
              <article key={f.decision_id} className={`${card} p-5 ${f.severity === 'potential_conflict' ? 'border-amber-500/40' : ''}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge color={f.severity === 'potential_conflict' ? 'amber' : 'gray'}>{f.headline}</Badge>
                  <Badge color={badge.color}>{badge.label}</Badge>
                </div>
                <h3 className="mt-2 text-lg font-medium">
                  <Link to={`../decisions/${f.decision_id}`} relative="path" className="hover:underline">{f.topic}</Link>
                </h3>
                {f.decision && <p className="text-sm">Decision: <strong>{f.decision}</strong></p>}

                <h4 className="mt-4 text-sm font-medium">Why it may be affected</h4>
                <ul className="mt-1 space-y-2 text-sm">
                  {f.triggers.map((t, i) => (
                    <li key={i}>
                      <span className="font-medium">{SIGNAL[t.signal] ?? t.signal}:</span> {t.detail}
                      {t.lines.length > 0 && (
                        <pre className="mt-1 overflow-x-auto rounded-md bg-zinc-100 p-2 text-xs dark:bg-zinc-900">{t.lines.join('\n')}</pre>
                      )}
                    </li>
                  ))}
                </ul>
                <p className={`mt-2 text-sm ${muted}`}>Triggered by: {f.triggered_by_files.map((p) => <code key={p} className="mr-2">{p}</code>)}</p>

                <h4 className="mt-4 text-sm font-medium">Historical reasoning</h4>
                {f.supporting_sources.length === 0 ? <p className={`text-sm ${muted}`}>No verified source is recorded.</p> : (
                  <ul className="mt-1 space-y-2 text-sm">
                    {f.supporting_sources.map((s, i) => (
                      <li key={i}>
                        <blockquote className={`border-l-2 border-zinc-300 pl-3 dark:border-zinc-700 ${muted}`}>{s.quote}</blockquote>
                        <ExternalLink href={s.url} className="text-xs">{s.author ? `@${s.author}` : 'source'} on GitHub</ExternalLink>
                        {s.verification_state !== 'verified' && <span className={`ml-2 text-xs ${muted}`}>({s.verification_state.replace('_', ' ')})</span>}
                      </li>
                    ))}
                  </ul>
                )}
              </article>
            )
          })}
        </div>
      )}
    </div>
  )
}
