import { useState } from 'react'
import { Link } from 'react-router-dom'

import { EvidenceItem } from '../components/Evidence'
import { ReviewForm } from '../components/ReviewForm'
import { Badge, Empty, ErrorBox, Spinner } from '../components/ui'
import { useApi } from '../hooks/useApi'
import { useRepo } from '../lib/repoContext'
import { ALT_STATUS, decisionBadge } from '../lib/decisionStatus'
import { card, link, muted } from '../lib/ui'
import { getDecision, listDecisions } from '../services/api'

function ConflictCard({ id, onChanged }: { id: number; onChanged: () => void }) {
  const { data: d, error, reload } = useApi((s) => getDecision(id, s), [id])
  const [open, setOpen] = useState(false)
  if (error) return <ErrorBox message={error} onRetry={reload} />
  if (!d) return <Spinner />
  const badge = decisionBadge(d)
  const positions = d.evidence.filter((e) => e.claim_type === 'position' || e.claim_type === 'alternative' || e.claim_type === 'rejection')
  return (
    <article className={`${card} p-5`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <Link to={`../decisions/${d.id}`} relative="path" className={`text-lg font-medium ${link}`}>{d.topic}</Link>
        <div className="flex flex-wrap gap-1.5">
          <Badge color={badge.color}>{badge.label}</Badge>
          {d.conflict_detected && <Badge color="amber">conflicting opinions</Badge>}
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-sm">
        <span className={muted}>Alternatives:</span>
        {d.alternatives.map((a) => <Badge key={a.name} color={ALT_STATUS[a.status]?.color ?? 'gray'}>{a.name}: {ALT_STATUS[a.status]?.label ?? a.status}</Badge>)}
      </div>
      <ul className="mt-4 grid gap-2 md:grid-cols-2">{positions.map((e, i) => <EvidenceItem key={i} e={e} />)}</ul>
      <div className="mt-4">
        <button onClick={() => setOpen((o) => !o)} className={`text-sm ${link}`}>{open ? 'Hide review form' : 'Review this decision'}</button>
        {open && <div className="mt-3"><ReviewForm decision={d} onReviewed={() => { reload(); onChanged() }} /></div>}
      </div>
    </article>
  )
}

export function ConflictReviewPage() {
  const { repo } = useRepo()
  const { data, error, loading, reload } = useApi((s) => listDecisions(repo.id, s), [repo.id])
  const queue = (data ?? []).filter((d) => d.requires_human_review || (d.conflict_detected && d.status === 'unresolved'))

  return (
    <div className="space-y-5">
      <p className={`max-w-3xl text-sm ${muted}`}>
        Decisions where participants disagree, or where the evidence does not establish an outcome. DeciTrace never
        resolves these itself: an outcome is recorded only by a reviewer whose write access GitHub confirms.
      </p>
      {loading && <Spinner />}
      {error && <ErrorBox message={error} onRetry={reload} />}
      {data && queue.length === 0 && <Empty title="Nothing needs review">No unresolved conflicts or unverified outcomes.</Empty>}
      <div className="space-y-4">{queue.map((d) => <ConflictCard key={d.id} id={d.id} onChanged={reload} />)}</div>
    </div>
  )
}
