import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { Badge, ErrorBox, ExternalLink, Spinner } from '../components/ui'
import { useRepo } from '../lib/repoContext'
import { SOURCE_LABEL } from '../lib/decisionStatus'
import { btnPrimary, card, input, muted } from '../lib/ui'
import { askQuestion } from '../services/api'
import type { AskResponse } from '../types/views'

interface Turn {
  question: string
  answer?: AskResponse
  error?: string
}

const SUGGESTIONS = [
  'Which decisions are still unresolved, and why?',
  'What alternatives were rejected, and for what reasons?',
  'Why was the current architecture chosen?',
  'Which decisions have no verified implementation?',
]

const CONFIDENCE = {
  supported: { label: 'Supported by verified decisions', color: 'green' },
  partial: { label: 'Partial: based on raw discussion only', color: 'amber' },
  insufficient: { label: 'Insufficient evidence', color: 'gray' },
} as const

function renderAnswer(text: string, ids: Set<string>) {
  return text.split(/(\[S\d+\])/g).map((part, i) => {
    const m = part.match(/^\[(S\d+)\]$/)
    return m && ids.has(m[1]) ? <a key={i} href={`#cite-${m[1]}`} className="font-mono text-xs text-indigo-600 dark:text-indigo-400">[{m[1]}]</a> : part
  })
}

function Answer({ a }: { a: AskResponse }) {
  const conf = CONFIDENCE[a.confidence]
  const ids = new Set(a.citations.map((c) => c.id))
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1.5">
        <Badge color={conf.color}>{conf.label}</Badge>
        {a.retrieval.mode && <Badge>{a.retrieval.mode === 'hybrid' ? 'hybrid search' : 'full-text search'}</Badge>}
        {a.model && <Badge>{a.model}</Badge>}
      </div>
      {a.conflicts.length > 0 && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-800 dark:text-amber-300">
          <p className="font-medium">Unresolved conflict</p>
          {a.conflicts.map((c) => (
            <p key={c.decision_id}>
              <Link to={`../decisions/${c.decision_id}`} relative="path" className="underline">{c.topic}</Link>: {c.alternatives.join(' vs ')}. No
              authoritative resolution exists; DeciTrace does not pick one.
            </p>
          ))}
        </div>
      )}
      <p className={`whitespace-pre-wrap leading-relaxed ${a.insufficient_evidence ? muted : ''}`}>{renderAnswer(a.answer, ids)}</p>
      {a.citations.length > 0 && (
        <ol className="space-y-2">
          {a.citations.map((c) => (
            <li key={c.id} id={`cite-${c.id}`} className={`${card} p-3 text-sm`}>
              <p>
                <span className="mr-2 font-mono text-xs">[{c.id}]</span>
                {c.url ? <ExternalLink href={c.url}>{SOURCE_LABEL[c.source_type] ?? c.source_type}{c.source_number ? ` #${c.source_number}` : ''}</ExternalLink>
                  : <span>{SOURCE_LABEL[c.source_type] ?? c.source_type}{c.source_number ? ` ${c.source_number}` : ''}</span>}
                <span className={`ml-2 ${muted}`}>{c.title}</span>
              </p>
              <p className={`mt-1 line-clamp-3 ${muted}`}>{c.evidence}</p>
            </li>
          ))}
        </ol>
      )}
      {a.warnings.length > 0 && <ul className={`space-y-0.5 text-xs ${muted}`}>{a.warnings.map((w, i) => <li key={i}>⚠ {w}</li>)}</ul>}
    </div>
  )
}

export function AskPage() {
  const { repo } = useRepo()
  const [turns, setTurns] = useState<Turn[]>([])
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const bottom = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // Block body on purpose: newer browsers return a Promise from scrollIntoView, which React would
    // mistake for a cleanup function. Skip the scroll on first render so the page opens at the top.
    if (turns.length) bottom.current?.scrollIntoView({ behavior: 'smooth' })
  }, [turns])

  async function ask(q: string) {
    const text = q.trim()
    if (!text || busy) return
    setQuestion('')
    setBusy(true)
    setTurns((t) => [...t, { question: text }])
    try {
      const answer = await askQuestion(repo.id, text)
      setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? { ...turn, answer } : turn)))
    } catch (err) {
      const error = err instanceof Error ? err.message : 'The question could not be answered.'
      setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? { ...turn, error } : turn)))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      {turns.length === 0 && (
        <div className="py-6">
          <h2 className="text-lg font-semibold">Ask about {repo.full_name}</h2>
          <p className={`mt-1 text-sm ${muted}`}>
            Answers use only this repository's ingested history and cite their sources. When the evidence does not answer
            the question, DeciTrace says so.
          </p>
          <div className="mt-5 grid gap-2 sm:grid-cols-2">
            {SUGGESTIONS.map((s) => (
              <button key={s} onClick={() => ask(s)} className={`${card} p-3 text-left text-sm hover:border-indigo-400/60`}>{s}</button>
            ))}
          </div>
        </div>
      )}
      <div className="space-y-8">
        {turns.map((t, i) => (
          <div key={i} className="space-y-3">
            <p className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-sm bg-indigo-600 px-4 py-2 text-sm text-white">{t.question}</p>
            <div className={`${card} p-4`}>
              {t.answer ? <Answer a={t.answer} /> : t.error ? <ErrorBox message={t.error} /> : <Spinner label="Retrieving evidence and generating an answer…" />}
            </div>
          </div>
        ))}
      </div>
      <div ref={bottom} />
      <form onSubmit={(e: FormEvent) => { e.preventDefault(); ask(question) }} className="sticky bottom-0 mt-6 flex gap-2 bg-zinc-50 py-4 dark:bg-zinc-950">
        <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Why was this built this way?" className={input}
          aria-label="Question" disabled={busy} maxLength={1000} />
        <button type="submit" className={btnPrimary} disabled={busy || question.trim().length < 3}>{busy ? 'Answering…' : 'Ask'}</button>
      </form>
    </div>
  )
}
