import { useState } from 'react'

import { ConnectRepositoryForm } from '../components/ConnectRepositoryForm'
import { RepositoryList } from '../components/RepositoryList'
import { RepositoryPanel } from '../components/RepositoryPanel'
import { StatusBadge } from '../components/StatusBadge'
import { useHealth } from '../hooks/useHealth'
import { useRepositories } from '../hooks/useRepositories'

function SystemStatus() {
  const { state, retry } = useHealth()
  if (state.kind === 'loading') return <p className="text-sm text-slate-500">Checking backend…</p>
  if (state.kind === 'error')
    return (
      <div className="flex items-center gap-3 rounded-md bg-rose-50 p-3 text-sm text-rose-800">
        <span>{state.message}</span>
        <button onClick={retry} className="rounded-md bg-rose-600 px-2 py-1 text-white hover:bg-rose-700">
          Retry
        </button>
      </div>
    )
  const { database, github_token_configured } = state.health
  return (
    <div className="flex flex-wrap gap-2 text-sm">
      <StatusBadge ok={database.reachable} label={database.reachable ? 'database connected' : 'database unreachable'} />
      <StatusBadge ok={database.pgvector} label={database.pgvector ? 'pgvector enabled' : 'pgvector missing'} />
      <StatusBadge
        ok={github_token_configured}
        label={github_token_configured ? 'GitHub token set' : 'no GitHub token: 60 requests/hour, sampled ingestion'}
      />
    </div>
  )
}

export function HomePage() {
  const { repos, error, refresh } = useRepositories()
  const [selected, setSelected] = useState<number | null>(null)
  const current = selected ?? repos?.[0]?.id ?? null

  return (
    <div className="space-y-6">
      <SystemStatus />
      <ConnectRepositoryForm
        onConnected={(repo) => {
          setSelected(repo.id)
          refresh()
        }}
      />
      <div className="grid gap-6 md:grid-cols-[16rem_1fr]">
        <div>
          <h2 className="mb-2 text-sm font-semibold text-slate-600">Repositories</h2>
          {error && <p className="rounded-md bg-rose-50 p-3 text-sm text-rose-800">{error}</p>}
          {!error && !repos && <p className="text-sm text-slate-500">Loading…</p>}
          {repos && <RepositoryList repos={repos} selected={current} onSelect={setSelected} />}
        </div>
        <div>{current !== null && <RepositoryPanel key={current} id={current} onChanged={refresh} />}</div>
      </div>
    </div>
  )
}
