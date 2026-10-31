import type { StageProgress, SyncJob } from '../types/repository'

const STAGES: [string, string][] = [
  ['metadata', 'Repository connected'],
  ['issues', 'Fetching issues'],
  ['issue_comments', 'Fetching issue comments'],
  ['pull_requests', 'Fetching pull requests'],
  ['discussions', 'Fetching discussions'],
  ['commits', 'Fetching commits'],
  ['code', 'Fetching code'],
  ['links', 'Linking related records'],
]

const ICON: Record<string, string> = { pending: '○', running: '◌', done: '✓', skipped: '–', failed: '✕' }
const COLOR: Record<string, string> = {
  pending: 'text-slate-400',
  running: 'text-indigo-600 animate-pulse',
  done: 'text-emerald-600',
  skipped: 'text-slate-500',
  failed: 'text-rose-600',
}

function detail(p: StageProgress): string {
  if (p.skipped) return p.skipped
  if (p.message) return p.message
  const parts: string[] = []
  if (typeof p.fetched === 'number') parts.push(`${p.fetched} fetched`)
  if (typeof p.review_comments === 'number') parts.push(`${p.review_comments} review comments`)
  if (typeof p.comments === 'number') parts.push(`${p.comments} comments`)
  if (typeof p.selected === 'number') parts.push(`${p.selected} files selected, ${p.unchanged ?? 0} unchanged`)
  if (typeof p.verified === 'number') parts.push(`${p.verified} verified links, ${p.possible ?? 0} possible`)
  if (p.truncated) parts.push('limited to the most recent items')
  return parts.join(' · ')
}

export function SyncProgress({ job }: { job: SyncJob }) {
  const final = {
    completed: ['Processing completed', 'bg-emerald-50 text-emerald-800'],
    partial: ['Processing completed with errors', 'bg-amber-50 text-amber-800'],
    failed: ['Processing failed', 'bg-rose-50 text-rose-800'],
  }[job.status as 'completed' | 'partial' | 'failed']

  return (
    <div>
      <ol className="space-y-1.5 text-sm">
        {STAGES.map(([key, label]) => {
          const p = (job.progress[key] ?? { status: 'pending' }) as StageProgress
          return (
            <li key={key} className="flex gap-2">
              <span aria-hidden className={`w-4 text-center ${COLOR[p.status] ?? ''}`}>
                {ICON[p.status] ?? '○'}
              </span>
              <span className={p.status === 'pending' ? 'text-slate-400' : ''}>{label}</span>
              <span className="text-slate-500">{detail(p)}</span>
            </li>
          )
        })}
      </ol>
      {final && <p className={`mt-3 rounded-md p-2 text-sm font-medium ${final[1]}`}>{final[0]}</p>}
      {job.errors.length > 0 && (
        <ul className="mt-2 space-y-1 text-sm text-rose-700">
          {job.errors.map((e, i) => (
            <li key={i}>
              {e.stage}: {e.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
