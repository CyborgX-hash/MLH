import { useEffect, useState } from 'react'

import { getCodeMap, getRelated } from '../services/api'
import type { CodeLink, CodeMap, RecordInfo, RelatedGraph } from '../types/links'

const KIND: Record<string, string> = { issue: 'Issue', pull_request: 'PR', discussion: 'Discussion', commit: 'Commit' }

function recordLabel(r: RecordInfo | undefined): string {
  if (!r) return 'unknown record'
  if (r.kind === 'commit') return `Commit ${r.sha?.slice(0, 7)}`
  return `${KIND[r.kind] ?? r.kind} #${r.number}`
}

function Related({ graph }: { graph: RelatedGraph }) {
  const byKey = new Map(graph.records.map((r) => [`${r.kind}:${r.id}`, r]))
  const verified = graph.links.filter((l) => l.verification_status === 'verified')
  const possible = graph.links.filter((l) => l.verification_status === 'possible')
  const cited = graph.records.filter((r) => r.cited)

  const row = (l: RelatedGraph['links'][number], i: number) => {
    const s = byKey.get(`${l.source.kind}:${l.source.id}`)
    const t = byKey.get(`${l.target.kind}:${l.target.id}`)
    return (
      <li key={i} className="text-sm">
        <a href={s?.url ?? undefined} target="_blank" rel="noreferrer" className="text-indigo-700 hover:underline">
          {recordLabel(s)}
        </a>{' '}
        <span className="text-slate-500">{l.relation.replace('_', ' ')}</span>{' '}
        <a href={t?.url ?? undefined} target="_blank" rel="noreferrer" className="text-indigo-700 hover:underline">
          {recordLabel(t)}
        </a>
        {t?.title && <span className="text-slate-500"> ({t.title})</span>}
        <span className="ml-1 text-xs text-slate-400">
          {l.signal.replaceAll('_', ' ')}
          {l.evidence.terms && `: ${l.evidence.terms.join(', ')}`}
          {l.evidence.paths && `: ${l.evidence.paths.join(', ')}`}
        </span>
        {l.evidence.snippet && <q className="block pl-4 text-xs text-slate-500">{l.evidence.snippet}</q>}
      </li>
    )
  }

  return (
    <section>
      <h4 className="mb-1 text-sm font-medium">Decision history across sources</h4>
      <p className="text-xs text-slate-500">
        Cited: {cited.map((r) => recordLabel(r)).join(', ') || 'none'}
      </p>
      {verified.length > 0 ? (
        <ul className="mt-1 space-y-1">{verified.map(row)}</ul>
      ) : (
        <p className="text-sm text-slate-500">No explicitly linked records.</p>
      )}
      {possible.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-sm text-amber-800">
            {possible.length} possible connection{possible.length > 1 ? 's' : ''} (not verified: shared files, terms or wording)
          </summary>
          <ul className="mt-1 space-y-1 opacity-80">{possible.map(row)}</ul>
        </details>
      )}
    </section>
  )
}

function FileRow({ f }: { f: CodeLink }) {
  return (
    <li className="text-sm">
      <code>{f.path ?? '(commit)'}</code>
      {f.change_type && <span className="text-slate-500"> {f.change_type}</span>}
      {f.deleted && <span className="ml-1 rounded bg-slate-200 px-1 text-xs">deleted since</span>}
      {!f.deleted && f.current_path && f.current_path !== f.path && (
        <span className="text-slate-600"> → now <code>{f.current_path}</code></span>
      )}
      {f.changed_after.length > 0 && (
        <span className="ml-1 text-xs text-amber-800">changed again in PR {f.changed_after.map((n) => `#${n}`).join(', ')}</span>
      )}
    </li>
  )
}

function Implementation({ map }: { map: CodeMap }) {
  const group = (rows: CodeLink[]) => {
    const out = new Map<string, CodeLink[]>()
    for (const r of rows) {
      const k = r.pr_number ? `pr:${r.pr_number}` : `commit:${r.commit_sha}`
      out.set(k, [...(out.get(k) ?? []), r])
    }
    return [...out.values()]
  }
  const block = (rows: CodeLink[], i: number) => {
    const first = rows[0]
    return (
      <div key={i} className="rounded-md bg-slate-50 p-2">
        <p className="text-sm">
          {first.pr_number ? (
            <a href={first.pr_url ?? undefined} target="_blank" rel="noreferrer" className="font-medium text-indigo-700 hover:underline">
              PR #{first.pr_number}
            </a>
          ) : (
            <span className="font-medium">Commit</span>
          )}
          {first.commit_url && (
            <a href={first.commit_url} target="_blank" rel="noreferrer" className="ml-2 text-xs text-indigo-700 hover:underline">
              commit {first.commit_sha?.slice(0, 7)}
            </a>
          )}
          {first.merged_at && <span className="ml-2 text-xs text-slate-500">merged {new Date(first.merged_at).toLocaleDateString()}</span>}
        </p>
        <p className="text-xs text-slate-500">why: {first.basis}</p>
        <ul className="mt-1">{rows.filter((r) => r.path).map((r, j) => <FileRow key={j} f={r} />)}</ul>
      </div>
    )
  }
  return (
    <section>
      <h4 className="mb-1 text-sm font-medium">Implementation</h4>
      {map.message ? (
        <p className="rounded-md bg-slate-100 p-2 text-sm text-slate-700">{map.message}</p>
      ) : (
        <div className="space-y-2">{group(map.verified).map(block)}</div>
      )}
      {map.possible.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-sm text-amber-800">Possible mappings (not verified)</summary>
          <div className="mt-1 space-y-2 opacity-80">{group(map.possible).map(block)}</div>
        </details>
      )}
      {map.notes.length > 0 && (
        <ul className="mt-1 list-disc pl-5 text-xs text-slate-500">{map.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
      )}
    </section>
  )
}

export function DecisionContext({ decisionId }: { decisionId: number }) {
  const [graph, setGraph] = useState<RelatedGraph | null>(null)
  const [map, setMap] = useState<CodeMap | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const c = new AbortController()
    Promise.all([getRelated(decisionId, c.signal), getCodeMap(decisionId, c.signal)])
      .then(([g, m]) => {
        setGraph(g)
        setMap(m)
      })
      .catch((err: unknown) => !c.signal.aborted && setError(err instanceof Error ? err.message : 'Error'))
    return () => c.abort()
  }, [decisionId])

  if (error) return <p className="rounded-md bg-rose-50 p-2 text-sm text-rose-800">{error}</p>
  if (!graph || !map) return <p className="text-sm text-slate-500">Loading history and implementation…</p>
  return (
    <div className="space-y-4">
      <Related graph={graph} />
      <Implementation map={map} />
    </div>
  )
}
