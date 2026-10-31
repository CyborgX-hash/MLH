import type { Repository } from '../types/repository'

const BADGE: Record<string, string> = {
  queued: 'bg-slate-100 text-slate-700',
  running: 'bg-indigo-100 text-indigo-800',
  completed: 'bg-emerald-100 text-emerald-800',
  partial: 'bg-amber-100 text-amber-800',
  failed: 'bg-rose-100 text-rose-800',
}

interface Props {
  repos: Repository[]
  selected: number | null
  onSelect: (id: number) => void
}

export function RepositoryList({ repos, selected, onSelect }: Props) {
  if (repos.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
        No repositories yet. Connect one above to start recovering its decisions.
      </p>
    )
  }
  return (
    <ul className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">
      {repos.map((r) => (
        <li key={r.id}>
          <button
            onClick={() => onSelect(r.id)}
            className={`flex w-full items-center justify-between gap-2 px-4 py-3 text-left hover:bg-slate-50 ${
              selected === r.id ? 'bg-indigo-50' : ''
            }`}
          >
            <span className="truncate font-medium">{r.full_name}</span>
            {r.latest_job && (
              <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${BADGE[r.latest_job.status] ?? ''}`}>
                {r.latest_job.status}
              </span>
            )}
          </button>
        </li>
      ))}
    </ul>
  )
}
