import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { Badge, Empty, ErrorBox, Spinner } from '../components/ui'
import { useApi } from '../hooks/useApi'
import { btnPrimary, card, cardPad, input, muted } from '../lib/ui'
import { connectRepository, getHealth, listRepositories } from '../services/api'

const JOB_COLOR = { queued: 'gray', running: 'blue', completed: 'green', partial: 'amber', failed: 'red' } as const

export function ConnectPage() {
  const navigate = useNavigate()
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const repos = useApi((s) => listRepositories(s), [])
  const health = useApi((s) => getHealth(s), [])

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const repo = await connectRepository(url.trim())
      navigate(`/repos/${repo.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not connect the repository.')
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-10 px-4 py-10">
      <form onSubmit={submit} className={`${card} p-6`} noValidate>
        <h1 className="text-xl font-semibold tracking-tight">Connect a GitHub repository</h1>
        <p className={`mt-1 text-sm ${muted}`}>
          DeciTrace collects the repository's history in the background and builds its knowledge base. You can ask
          questions once it has finished.
        </p>
        <label htmlFor="repo-url" className="mt-5 block text-sm font-medium">Repository URL</label>
        <div className="mt-1.5 flex flex-col gap-2 sm:flex-row">
          <input
            id="repo-url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://github.com/psf/requests"
            className={input}
            disabled={busy}
            aria-invalid={!!error}
            aria-describedby={error ? 'connect-error' : undefined}
          />
          <button type="submit" className={btnPrimary} disabled={busy || !url.trim()}>
            {busy ? 'Checking repository…' : 'Connect'}
          </button>
        </div>
        {error && <div id="connect-error" className="mt-3"><ErrorBox message={error} /></div>}
        <div className={`mt-5 grid gap-3 text-sm sm:grid-cols-2 ${muted}`}>
          <p>
            <span className="font-medium text-zinc-700 dark:text-zinc-200">Public repositories only.</span> DeciTrace
            reads public data through GitHub's API and never posts anything back to the project.
          </p>
          <p>
            <span className="font-medium text-zinc-700 dark:text-zinc-200">Access limits.</span> Without a server-side
            GitHub token, GitHub allows 60 requests per hour, so DeciTrace samples the most recent activity and skips
            Discussions. Tokens stay on the server and are never sent to the browser.
          </p>
        </div>
        {health.data && (
          <div className="mt-4 flex flex-wrap gap-2">
            <Badge color={health.data.database.reachable ? 'green' : 'red'}>
              database {health.data.database.reachable ? 'connected' : 'unreachable'}
            </Badge>
            <Badge color={health.data.github_token_configured ? 'green' : 'amber'}>
              {health.data.github_token_configured ? 'GitHub token set' : 'no GitHub token: sampled ingestion'}
            </Badge>
          </div>
        )}
        {health.error && <div className="mt-4"><ErrorBox message={health.error} onRetry={health.reload} /></div>}
      </form>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">Connected repositories</h2>
        {repos.loading && <Spinner />}
        {repos.error && <ErrorBox message={repos.error} onRetry={repos.reload} />}
        {repos.data?.length === 0 && <Empty title="No repositories yet">Connect one above to start recovering its decisions.</Empty>}
        <ul className="grid gap-3 sm:grid-cols-2">
          {repos.data?.map((r) => (
            <li key={r.id}>
              <Link to={`/repos/${r.id}`} className={`${cardPad} block hover:border-indigo-400/60`}>
                <div className="flex items-start justify-between gap-2">
                  <span className="font-medium">{r.full_name}</span>
                  {r.latest_job && <Badge color={JOB_COLOR[r.latest_job.status]}>{r.latest_job.status}</Badge>}
                </div>
                {r.description && <p className={`mt-1 line-clamp-2 text-sm ${muted}`}>{r.description}</p>}
                <p className={`mt-2 text-xs ${muted}`}>
                  {r.last_synced_at ? `Last synced ${new Date(r.last_synced_at).toLocaleString()}` : 'Not synced yet'}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
