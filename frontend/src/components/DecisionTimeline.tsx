import { Link } from 'react-router-dom'

import { muted } from '../lib/ui'
import type { TimelineEvent } from '../types/views'
import { Badge, ExternalLink } from './ui'

const STYLE: Record<TimelineEvent['type'], { label: string; dot: string; color: 'blue' | 'gray' | 'red' | 'green' | 'amber' }> = {
  proposal: { label: 'Proposal', dot: 'bg-indigo-500', color: 'blue' },
  argument: { label: 'Argument', dot: 'bg-zinc-400', color: 'gray' },
  rejection: { label: 'Rejection', dot: 'bg-rose-500', color: 'red' },
  approval: { label: 'Approval', dot: 'bg-emerald-500', color: 'green' },
  implementation: { label: 'Implementation', dot: 'bg-emerald-500', color: 'green' },
  commit: { label: 'Commit', dot: 'bg-zinc-500', color: 'gray' },
  human_review: { label: 'Human review', dot: 'bg-amber-500', color: 'amber' },
  superseded: { label: 'Superseded', dot: 'bg-zinc-500', color: 'gray' },
}

function SourceLink({ ev }: { ev: TimelineEvent }) {
  if (ev.url?.startsWith('decision:')) {
    return <Link to={`../decisions/${ev.url.split(':')[1]}`} relative="path" className="text-indigo-600 hover:underline dark:text-indigo-400">open decision</Link>
  }
  if (ev.url) return <ExternalLink href={ev.url}>source on GitHub</ExternalLink>
  if (ev.source === 'decitrace_review') return <span className={muted}>recorded in DeciTrace</span>
  return null
}

export function DecisionTimeline({ events }: { events: TimelineEvent[] }) {
  if (events.length === 0) return <p className={`text-sm ${muted}`}>No dated events with verifiable sources.</p>
  return (
    <ol className="relative space-y-5 border-l border-zinc-200 pl-6 dark:border-zinc-800">
      {events.map((ev, i) => {
        const s = STYLE[ev.type]
        return (
          <li key={i} className="relative">
            <span className={`absolute -left-[1.85rem] top-1.5 h-2.5 w-2.5 rounded-full ring-4 ring-zinc-50 dark:ring-zinc-950 ${s.dot}`} aria-hidden />
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Badge color={s.color}>{s.label}</Badge>
              <span className="font-medium">{ev.label}</span>
              {!ev.verified && <Badge color="amber">not verified</Badge>}
            </div>
            <p className={`mt-0.5 text-xs ${muted}`}>
              {ev.at ? new Date(ev.at).toLocaleString() : 'date unknown'}
              {ev.author && <> · @{ev.author}</>} · <SourceLink ev={ev} />
            </p>
            {ev.quote && <blockquote className={`mt-1.5 border-l-2 border-zinc-300 pl-3 text-sm dark:border-zinc-700 ${muted}`}>{ev.quote}</blockquote>}
          </li>
        )
      })}
    </ol>
  )
}
