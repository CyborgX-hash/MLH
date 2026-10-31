import { useState } from 'react'

import { useApi } from '../hooks/useApi'
import { btn, cardPad, muted } from '../lib/ui'
import { getExtractionStatus, startExtraction } from '../services/api'
import { Badge, ErrorBox } from './ui'

const ACTIVE = (s?: string) => s === 'queued' || s === 'running'
const COLOR = { queued: 'gray', running: 'blue', completed: 'green', partial: 'amber', failed: 'red' } as const

export function ExtractionPanel({ repoId, onFinished }: { repoId: number; onFinished: () => void }) {
  const [error, setError] = useState<string | null>(null)
  const [version, setVersion] = useState(0)
  const status = useApi((s) => getExtractionStatus(repoId, s), [repoId, version], {
    pollWhile: (job) => {
      const running = ACTIVE(job?.status)
      if (!running && job) onFinished()
      return running
    },
    pollMs: 2500,
  })
  const job = status.data
  const running = ACTIVE(job?.status)

  async function start() {
    setError(null)
    try {
      await startExtraction(repoId, 5)
      setVersion((v) => v + 1)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start extraction.')
    }
  }

  return (
    <div className={cardPad}>
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-medium">Decision extraction</h2>
        <button onClick={start} disabled={running} className={btn}>{running ? 'Extracting…' : 'Extract decisions'}</button>
      </div>
      <p className={`mt-1 text-xs ${muted}`}>
        An open-weight model reads the most-discussed threads and proposes decisions. Only candidates whose cited
        comments check out are recorded; the rest are refused.
      </p>
      {error && <div className="mt-3"><ErrorBox message={error} /></div>}
      {status.error && <div className="mt-3"><ErrorBox message={status.error} onRetry={status.reload} /></div>}
      {job && (
        <div className="mt-3 space-y-1 text-sm">
          <p className="flex flex-wrap items-center gap-2">
            <Badge color={COLOR[job.status as keyof typeof COLOR] ?? 'gray'}>{job.status}</Badge>
            <span className={muted}>{job.model}</span>
          </p>
          <p>
            {job.threads_done}/{job.threads_total} threads · {job.candidates} candidates · {job.created} recorded ·{' '}
            {job.merged} merged · {job.refused} refused
          </p>
          {job.errors.map((e, i) => <p key={i} className="text-xs text-rose-600 dark:text-rose-400">{e.thread}: {e.message}</p>)}
        </div>
      )}
    </div>
  )
}
