import { useState } from 'react'
import { Link } from 'react-router-dom'

import { ExtractionPanel } from '../components/ExtractionPanel'
import { RepoNumbers } from '../components/RepoNumbers'
import { SyncProgress } from '../components/SyncProgress'
import { ErrorBox, Section, Spinner, Stat } from '../components/ui'
import { useApi } from '../hooks/useApi'
import { useRepo } from '../lib/repoContext'
import { btn, cardPad, link, muted } from '../lib/ui'
import { getOverview, syncRepository } from '../services/api'

// "extractor:qwen/qwen3.6-27b" → "AI extraction (qwen3.6-27b)"; "github:alice" → "@alice"
function actorLabel(actor: string) {
  if (actor.startsWith('extractor:')) {
    const model = actor.slice('extractor:'.length)
    return model === 'manual-ui-check' ? 'a hand-written test candidate' : `AI extraction (${model.split('/').pop()})`
  }
  return actor.startsWith('github:') ? `@${actor.slice('github:'.length)}` : actor
}

const EVENT_LABEL: Record<string, string> = {
  created: 'found',
  reviewed: 'reviewed',
  superseded: 'superseded',
  supersedes: 'now supersedes an earlier decision',
  merged_duplicate: 'gained evidence from a related discussion',
}

export function DashboardPage() {
  const { repo, reload } = useRepo()
  const jobStatus = repo.latest_job?.status
  const overview = useApi((s) => getOverview(repo.id, s), [repo.id, jobStatus])
  const [syncError, setSyncError] = useState<string | null>(null)
  const active = jobStatus === 'queued' || jobStatus === 'running'

  async function sync(full: boolean) {
    setSyncError(null)
    try {
      await syncRepository(repo.id, full)
      reload()
    } catch (err) {
      setSyncError(err instanceof Error ? err.message : 'Could not start the sync.')
    }
  }

  const c = overview.data?.counts
  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_22rem]">
      <div className="space-y-8">
        <Section title="Decisions">
          {overview.error && <ErrorBox message={overview.error} onRetry={overview.reload} />}
          {!c && !overview.error && <Spinner />}
          {c && (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat label="Decisions found" value={c.decisions} hint={`${c.accepted} accepted · ${c.superseded} superseded`} />
              <Stat label="Still unresolved" value={c.unresolved} hint="no maintainer stated an outcome" />
              <Stat label="Waiting for a maintainer" value={c.needs_review} hint="confirm in Conflict review" />
              <Stat label="Options rejected" value={c.rejected_alternatives} hint="with a recorded objection" />
            </div>
          )}
        </Section>

        <Section title="Repository numbers">
          {overview.data ? <RepoNumbers repo={repo} overview={overview.data} /> : !overview.error && <Spinner />}
        </Section>

        <Section title="Recent decision activity" aside={<Link to="decisions" className={`text-sm ${link}`}>All decisions</Link>}>
          {overview.data?.recent_activity.length === 0 && (
            <p className={`text-sm ${muted}`}>
              No decisions yet. Decisions appear here once candidates from the extraction pipeline pass evidence validation.
            </p>
          )}
          <ul className="space-y-2">
            {overview.data?.recent_activity.map((a, i) => (
              <li key={i} className="text-sm">
                <Link to={`decisions/${a.decision_id}`} className={link}>{a.topic}</Link>{' '}
                <span className={muted}>{EVENT_LABEL[a.event] ?? a.event} by {actorLabel(a.actor)} · {new Date(a.at).toLocaleString()}</span>
              </li>
            ))}
          </ul>
        </Section>
      </div>

      <aside className="space-y-6">
        <ExtractionPanel repoId={repo.id} onFinished={overview.reload} />
        <div className={cardPad}>
          <div className="flex items-center justify-between gap-2">
            <h2 className="font-medium">Sync status</h2>
            <div className="flex gap-2">
              <button onClick={() => sync(false)} disabled={active} className={btn}>{active ? 'Syncing…' : 'Sync'}</button>
              <button onClick={() => sync(true)} disabled={active} className={btn} title="Re-read everything, ignoring cursors">Full</button>
            </div>
          </div>
          {syncError && <div className="mt-3"><ErrorBox message={syncError} /></div>}
          <div className="mt-4">
            {repo.latest_job ? <SyncProgress job={repo.latest_job} /> : <p className={`text-sm ${muted}`}>Not synced yet.</p>}
          </div>
        </div>
        <div className={`${cardPad} text-sm`}>
          <h2 className="mb-2 font-medium">Repository</h2>
          <dl className="grid grid-cols-[7rem_1fr] gap-y-1.5">
            <dt className={muted}>Language</dt><dd>{repo.language ?? '—'}</dd>
            <dt className={muted}>License</dt><dd>{repo.license_spdx ?? '—'}</dd>
            <dt className={muted}>Stars</dt><dd>{repo.stars.toLocaleString()}</dd>
            <dt className={muted}>Default branch</dt><dd><code>{repo.default_branch}</code></dd>
            <dt className={muted}>Last synced</dt><dd>{repo.last_synced_at ? new Date(repo.last_synced_at).toLocaleString() : '—'}</dd>
          </dl>
        </div>
      </aside>
    </div>
  )
}
