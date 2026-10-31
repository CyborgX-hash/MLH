import { Suspense, lazy, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

// The graph library is large; load it only when the graph view is opened.
const DecisionGraph = lazy(() => import('../components/DecisionGraph').then((m) => ({ default: m.DecisionGraph })))
import { DecisionTimeline } from '../components/DecisionTimeline'
import { EvidenceItem } from '../components/Evidence'
import { ReviewForm } from '../components/ReviewForm'
import { Badge, ErrorBox, ExternalLink, Section, Spinner } from '../components/ui'
import { useApi } from '../hooks/useApi'
import { ALT_STATUS, SOURCE_LABEL, decisionBadge } from '../lib/decisionStatus'
import { card, cardPad, link, muted } from '../lib/ui'
import { getCodeMap, getDecision, getGraph, getRelated, getTimeline } from '../services/api'
import type { Decision } from '../types/decision'
import type { CodeLink, RecordInfo } from '../types/links'

function recordLabel(r: RecordInfo) {
  return r.kind === 'commit' ? `Commit ${r.sha?.slice(0, 7)}` : `${SOURCE_LABEL[r.kind] ?? r.kind} #${r.number}`
}

export function DecisionDetailPage() {
  const id = Number(useParams().decisionId)
  const [version, setVersion] = useState(0)
  const decision = useApi((s) => getDecision(id, s), [id, version])
  const timeline = useApi((s) => getTimeline(id, s), [id, version])
  const graph = useApi((s) => getGraph(id, s), [id, version])
  const related = useApi((s) => getRelated(id, s), [id, version])
  const code = useApi((s) => getCodeMap(id, s), [id, version])
  const [view, setView] = useState<'timeline' | 'graph'>('timeline')
  const [showPossible, setShowPossible] = useState(false)

  if (decision.error) return <ErrorBox message={decision.error} onRetry={decision.reload} />
  if (!decision.data) return <Spinner label="Loading decision…" />
  const d: Decision = decision.data
  const badge = decisionBadge(d)
  const positions = d.evidence.filter((e) => e.claim_type === 'position')
  const args = d.evidence.filter((e) => e.claim_type !== 'position')
  const contributors = [...new Map(d.evidence.filter((e) => e.author_login).map((e) => [e.author_login, e])).values()]
  const records = related.data?.records ?? []
  const byKind = (kinds: string[]) => records.filter((r) => kinds.includes(r.kind))
  const possibleIds = new Set(
    (related.data?.links ?? []).filter((l) => l.verification_status === 'possible').flatMap((l) => [`${l.source.kind}:${l.source.id}`, `${l.target.kind}:${l.target.id}`]),
  )
  const verifiedIds = new Set(
    (related.data?.links ?? []).filter((l) => l.verification_status === 'verified').flatMap((l) => [`${l.source.kind}:${l.source.id}`, `${l.target.kind}:${l.target.id}`]),
  )

  return (
    <div className="space-y-10">
      <div>
        <Link to=".." relative="path" className={`text-sm ${link}`}>← All decisions</Link>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Badge color={badge.color}>{badge.label}</Badge>
          {d.conflict_detected && <Badge color="amber">conflicting opinions</Badge>}
          {d.superseded_by_id && <Link to={`../${d.superseded_by_id}`} relative="path" className={`text-sm ${link}`}>superseded by decision {d.superseded_by_id}</Link>}
        </div>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">{d.topic}</h1>
        {d.problem && <p className={`mt-1 max-w-3xl ${muted}`}>Original problem: {d.problem}</p>}
        <p className="mt-3">
          Final decision: {d.decision ? <strong>{d.decision}</strong> : <em className={muted}>none established</em>}
          {d.status === 'unresolved' && <span className={`ml-2 text-sm ${muted}`}>No authoritative resolution exists in the sources.</span>}
        </p>
      </div>

      <div className="grid gap-8 lg:grid-cols-2">
        <Section title="Proposals and alternatives">
          {d.alternatives.length === 0 ? <p className={`text-sm ${muted}`}>No alternatives recorded.</p> : (
            <ul className={`${card} divide-y divide-zinc-200 dark:divide-zinc-800`}>
              {d.alternatives.map((a) => (
                <li key={a.name} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm">
                  <span className="font-medium">{a.name}</span>
                  <span className="flex flex-wrap items-center gap-2">
                    <Badge color={ALT_STATUS[a.status]?.color ?? 'gray'}>{ALT_STATUS[a.status]?.label ?? a.status}</Badge>
                    {a.status === 'rejected' && <span className={muted}>{a.rejection_reason ?? 'reason not recorded in the sources'}</span>}
                    {a.proposed_status !== a.status && <span className={`text-xs ${muted}`}>(extractor said {ALT_STATUS[a.proposed_status]?.label ?? a.proposed_status})</span>}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Section>
        <Section title="Contributors">
          {contributors.length === 0 ? <p className={`text-sm ${muted}`}>No attributed sources.</p> : (
            <ul className="flex flex-wrap gap-2">
              {contributors.map((e) => (
                <li key={e.author_login}>
                  <ExternalLink href={`https://github.com/${e.author_login}`} className={`${card} inline-block px-3 py-1.5 text-sm`}>
                    @{e.author_login}
                    {e.author_association && e.author_association !== 'NONE' && <span className={`ml-1 text-xs ${muted}`}>{e.author_association.toLowerCase()}</span>}
                  </ExternalLink>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>

      <Section
        title="History"
        aside={
          <div className="flex gap-1 rounded-lg border border-zinc-200 p-1 text-sm dark:border-zinc-800">
            {(['timeline', 'graph'] as const).map((v) => (
              <button key={v} onClick={() => setView(v)} className={`rounded-md px-2.5 py-1 ${view === v ? 'bg-zinc-200 font-medium dark:bg-zinc-800' : muted}`}>
                {v === 'timeline' ? 'Timeline' : 'Graph'}
              </button>
            ))}
          </div>
        }
      >
        {view === 'timeline' && (timeline.error ? <ErrorBox message={timeline.error} /> : timeline.data ? <DecisionTimeline events={timeline.data} /> : <Spinner />)}
        {view === 'graph' && (graph.error ? <ErrorBox message={graph.error} /> : graph.data ? (
          <>
            {graph.data.edges.some((e) => e.status === 'possible') && (
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={showPossible} onChange={(e) => setShowPossible(e.target.checked)} />
                Show {graph.data.edges.filter((e) => e.status === 'possible').length} possible connections (shared terms or files, not verified)
              </label>
            )}
            <Suspense fallback={<Spinner label="Loading graph…" />}>
              <DecisionGraph data={graph.data} decisionId={d.id} showPossible={showPossible} />
            </Suspense>
            <p className={`text-xs ${muted}`}>Only relationships established by the backend are drawn. Dashed edges are possible connections, not facts. Click a node to open its source.</p>
          </>
        ) : <Spinner />)}
      </Section>

      <div className="grid gap-8 lg:grid-cols-2">
        <Section title="Arguments and supporting evidence">
          {args.length === 0 ? <p className={`text-sm ${muted}`}>None.</p> : <ul className="space-y-2">{args.map((e, i) => <EvidenceItem key={i} e={e} />)}</ul>}
        </Section>
        <Section title="Positions (all sides kept)">
          {positions.length === 0 ? <p className={`text-sm ${muted}`}>None recorded.</p> : <ul className="space-y-2">{positions.map((e, i) => <EvidenceItem key={i} e={e} />)}</ul>}
        </Section>
      </div>

      <div className="grid gap-8 lg:grid-cols-2">
        <Section title="Related issues, discussions and commits">
          {related.error && <ErrorBox message={related.error} />}
          {related.data && (
            <ul className="space-y-1.5 text-sm">
              {[...byKind(['issue']), ...byKind(['discussion']), ...byKind(['pull_request']), ...byKind(['commit'])].map((r) => {
                const key = `${r.kind}:${r.id}`
                const possibleOnly = possibleIds.has(key) && !verifiedIds.has(key) && !r.cited
                return (
                  <li key={key} className={possibleOnly ? 'opacity-70' : ''}>
                    {r.url ? <ExternalLink href={r.url}>{recordLabel(r)}</ExternalLink> : recordLabel(r)}{' '}
                    <span className={muted}>{r.title}</span>{' '}
                    {r.cited && <Badge color="blue">cited</Badge>}
                    {possibleOnly && <Badge color="amber">possible connection</Badge>}
                  </li>
                )
              })}
              {records.length === 0 && <li className={muted}>No related records.</li>}
            </ul>
          )}
        </Section>
        <Section title="Implementation">
          {code.error && <ErrorBox message={code.error} />}
          {code.data && (
            <div className="space-y-3 text-sm">
              {code.data.message ? <p className={`${cardPad} ${muted}`}>{code.data.message}</p> : <CodeLinks rows={code.data.verified} />}
              {code.data.possible.length > 0 && (
                <details>
                  <summary className="cursor-pointer text-amber-700 dark:text-amber-300">Possible mappings (not verified)</summary>
                  <div className="mt-2 opacity-80"><CodeLinks rows={code.data.possible} /></div>
                </details>
              )}
              {code.data.notes.map((n, i) => <p key={i} className={`text-xs ${muted}`}>{n}</p>)}
            </div>
          )}
        </Section>
      </div>

      {(d.validation_notes.length > 0 || d.reviews.length > 0 || d.history.length > 0) && (
        <div className="grid gap-8 lg:grid-cols-2">
          <Section title="Validation notes">
            {d.validation_notes.length === 0 ? <p className={`text-sm ${muted}`}>None.</p> :
              <ul className={`list-disc space-y-1 pl-5 text-sm ${muted}`}>{d.validation_notes.map((n, i) => <li key={i}>{n}</li>)}</ul>}
          </Section>
          <Section title="Audit history">
            <ol className={`space-y-1 text-sm ${muted}`}>
              {d.history.map((h, i) => (
                <li key={i}>{new Date(h.created_at).toLocaleString()}: {h.event.replace('_', ' ')} by {h.actor}
                  {typeof h.snapshot.status === 'string' && <> (was {h.snapshot.status})</>}</li>
              ))}
            </ol>
          </Section>
        </div>
      )}

      {d.status !== 'superseded' && (
        <Section title="Human review">
          <div className={cardPad}>
            <ReviewForm decision={d} onReviewed={() => setVersion((v) => v + 1)} />
          </div>
        </Section>
      )}
    </div>
  )
}

function CodeLinks({ rows }: { rows: CodeLink[] }) {
  const groups = new Map<string, CodeLink[]>()
  for (const r of rows) {
    const k = r.pr_number ? `pr:${r.pr_number}` : `commit:${r.commit_sha}`
    groups.set(k, [...(groups.get(k) ?? []), r])
  }
  return (
    <div className="space-y-2">
      {[...groups.values()].map((g, i) => {
        const f = g[0]
        return (
          <div key={i} className={`${card} p-3`}>
            <p>
              {f.pr_number && f.pr_url ? <ExternalLink href={f.pr_url}>PR #{f.pr_number}</ExternalLink> : <span>Commit</span>}
              {f.commit_url && <ExternalLink href={f.commit_url} className="ml-2 text-xs">commit {f.commit_sha?.slice(0, 7)}</ExternalLink>}
              {f.merged_at && <span className={`ml-2 text-xs ${muted}`}>merged {new Date(f.merged_at).toLocaleDateString()}</span>}
            </p>
            <p className={`text-xs ${muted}`}>why: {f.basis}</p>
            <ul className="mt-1.5 space-y-0.5">
              {g.filter((r) => r.path).map((r, j) => (
                <li key={j}>
                  <code>{r.path}</code> <span className={muted}>{r.change_type}</span>
                  {r.deleted && <Badge>deleted since</Badge>}
                  {!r.deleted && r.current_path && r.current_path !== r.path && <span className={muted}> → now <code>{r.current_path}</code></span>}
                  {r.changed_after.length > 0 && <span className="ml-1 text-xs text-amber-700 dark:text-amber-300">changed again in {r.changed_after.map((n) => `#${n}`).join(', ')}</span>}
                </li>
              ))}
            </ul>
          </div>
        )
      })}
    </div>
  )
}
