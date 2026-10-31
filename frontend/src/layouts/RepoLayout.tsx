import { NavLink, Outlet, useParams } from 'react-router-dom'

import { Badge, ErrorBox, ExternalLink, Spinner } from '../components/ui'
import { useApi } from '../hooks/useApi'
import type { RepoContext } from '../lib/repoContext'
import { muted } from '../lib/ui'
import { getRepository } from '../services/api'

const ACTIVE = (s?: string) => s === 'queued' || s === 'running'

export function RepoLayout() {
  const id = Number(useParams().repoId)
  const { data: repo, error, reload } = useApi((signal) => getRepository(id, signal), [id], {
    pollWhile: (r) => ACTIVE(r.latest_job?.status),
  })

  const tab = ({ isActive }: { isActive: boolean }) =>
    `shrink-0 whitespace-nowrap border-b-2 px-1 pb-2.5 text-sm ${isActive ? 'border-indigo-500 font-medium' : `border-transparent ${muted} hover:text-zinc-900 dark:hover:text-zinc-100`}`

  if (error) return <div className="mx-auto max-w-7xl p-4"><ErrorBox message={error} onRetry={reload} /></div>
  if (!repo) return <div className="mx-auto max-w-7xl p-4"><Spinner label="Loading repository…" /></div>

  return (
    <div className="mx-auto max-w-7xl px-4 pb-16">
      <div className="flex flex-wrap items-end justify-between gap-3 pt-6">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">
            <ExternalLink href={repo.html_url} className="!text-inherit">{repo.full_name}</ExternalLink>
          </h1>
          {repo.description && <p className={`mt-0.5 text-sm ${muted}`}>{repo.description}</p>}
        </div>
        {repo.latest_job && ACTIVE(repo.latest_job.status) && <Badge color="blue">Syncing: {repo.latest_job.stage_label}</Badge>}
      </div>
      <nav className="mt-5 flex gap-5 overflow-x-auto border-b border-zinc-200 dark:border-zinc-800">
        <NavLink end to="" className={tab}>Dashboard</NavLink>
        <NavLink to="decisions" className={tab}>Decisions</NavLink>
        <NavLink to="ask" className={tab}>Ask DeciTrace</NavLink>
        <NavLink to="conflicts" className={tab}>Conflict review</NavLink>
        <NavLink to="pr-impact" className={tab}>PR impact</NavLink>
      </nav>
      <div className="pt-6">
        <Outlet context={{ repo, reload } satisfies RepoContext} />
      </div>
    </div>
  )
}
