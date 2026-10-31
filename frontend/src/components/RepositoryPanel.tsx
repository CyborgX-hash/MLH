import { useState } from 'react'

import { useRepositoryDetail } from '../hooks/useRepositoryDetail'
import { syncRepository } from '../services/api'
import { DecisionList } from './DecisionList'
import { SyncProgress } from './SyncProgress'

export function RepositoryPanel({ id, onChanged }: { id: number; onChanged: () => void }) {
  const { repo, error, refresh } = useRepositoryDetail(id)
  const [syncError, setSyncError] = useState<string | null>(null)

  if (error) return <p className="rounded-md bg-rose-50 p-4 text-rose-800">{error}</p>
  if (!repo) return <p className="text-slate-500">Loading repository…</p>

  const job = repo.latest_job
  const active = job?.status === 'queued' || job?.status === 'running'

  async function sync(full: boolean) {
    setSyncError(null)
    try {
      await syncRepository(id, full)
      refresh()
      onChanged()
    } catch (err) {
      setSyncError(err instanceof Error ? err.message : 'Could not start the sync.')
    }
  }

  const counts: [string, number][] = [
    ['Issues', repo.counts.issues],
    ['Pull requests', repo.counts.pull_requests],
    ['Comments & reviews', repo.counts.comments],
    ['Discussions', repo.counts.discussions],
    ['Commits', repo.counts.commits],
    ['Source files', repo.counts.source_files],
  ]

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <a href={repo.html_url} target="_blank" rel="noreferrer" className="text-lg font-semibold hover:underline">
            {repo.full_name}
          </a>
          {repo.description && <p className="text-sm text-slate-600">{repo.description}</p>}
          <p className="mt-1 text-xs text-slate-500">
            {[repo.language, repo.license_spdx, `★ ${repo.stars}`, `branch ${repo.default_branch}`]
              .filter(Boolean)
              .join(' · ')}
            {repo.last_synced_at && ` · last synced ${new Date(repo.last_synced_at).toLocaleString()}`}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => sync(false)}
            disabled={active}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-50"
          >
            {active ? 'Syncing…' : 'Sync new activity'}
          </button>
          <button
            onClick={() => sync(true)}
            disabled={active}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-50"
          >
            Full re-sync
          </button>
        </div>
      </div>
      {syncError && <p className="mt-3 rounded-md bg-rose-50 p-2 text-sm text-rose-800">{syncError}</p>}

      <dl className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3">
        {counts.map(([label, n]) => (
          <div key={label} className="rounded-md bg-slate-50 p-3">
            <dt className="text-xs text-slate-500">{label}</dt>
            <dd className="text-xl font-semibold">{n}</dd>
          </div>
        ))}
      </dl>

      <h3 className="mt-6 mb-2 font-medium">Ingestion</h3>
      {job ? <SyncProgress job={job} /> : <p className="text-sm text-slate-500">Not synced yet.</p>}

      <h3 className="mt-6 mb-2 font-medium">Decisions</h3>
      <DecisionList repoId={repo.id} />
    </section>
  )
}
