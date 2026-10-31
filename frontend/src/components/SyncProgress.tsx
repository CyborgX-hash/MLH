import { muted } from '../lib/ui'
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
  ['index', 'Building the knowledge base'],
]

const ICON: Record<string, string> = { pending: '○', running: '◌', done: '✓', skipped: '–', failed: '✕' }
const COLOR: Record<string, string> = {
  pending: 'text-zinc-400 dark:text-zinc-600',
  running: 'text-indigo-500 animate-pulse',
  done: 'text-emerald-600 dark:text-emerald-400',
  skipped: 'text-zinc-500',
  failed: 'text-rose-600 dark:text-rose-400',
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
  if (typeof p.chunks === 'number')
    parts.push(`${p.chunks} chunks, ${p.vector_search ? `${p.embedded} embedded` : 'full-text search only'}`)
  if (p.truncated) parts.push('limited to the most recent items')
  return parts.join(' · ')
}

const FINAL = {
  completed: ['Processing completed', 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'],
  partial: ['Processing completed with errors', 'border-amber-500/30 bg-amber-500/10 text-amber-800 dark:text-amber-300'],
  failed: ['Processing failed', 'border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-300'],
} as const

export function SyncProgress({ job }: { job: SyncJob }) {
  const final = FINAL[job.status as keyof typeof FINAL]
  return (
    <div>
      <ol className="space-y-1.5 text-sm">
        {STAGES.map(([key, label]) => {
          const p = (job.progress[key] ?? { status: 'pending' }) as StageProgress
          return (
            <li key={key} className="flex flex-wrap gap-x-2">
              <span aria-hidden className={`w-4 text-center ${COLOR[p.status] ?? ''}`}>{ICON[p.status] ?? '○'}</span>
              <span className={p.status === 'pending' ? 'text-zinc-400 dark:text-zinc-600' : ''}>{label}</span>
              <span className={muted}>{detail(p)}</span>
            </li>
          )
        })}
      </ol>
      {final && <p className={`mt-3 rounded-lg border p-2 text-sm font-medium ${final[1]}`}>{final[0]}</p>}
      {job.errors.length > 0 && (
        <ul className="mt-2 space-y-1 text-sm text-rose-600 dark:text-rose-400">
          {job.errors.map((e, i) => <li key={i}>{e.stage}: {e.message}</li>)}
        </ul>
      )}
    </div>
  )
}
