import { muted } from '../lib/ui'
import type { RepositoryDetail } from '../types/repository'
import type { Overview } from '../types/views'
import { Badge, ExternalLink } from './ui'

const fmt = (n: number | null | undefined) => (typeof n === 'number' ? n.toLocaleString() : '—')
const sum = (...xs: (number | null | undefined)[]) =>
  xs.every((x) => typeof x === 'number') ? (xs as number[]).reduce((a, b) => a + b, 0) : null

function Row({ label, github, analysed, note }: { label: string; github: string; analysed?: string; note?: string }) {
  return (
    <tr className="border-t border-zinc-200 dark:border-zinc-800">
      <td className="py-2 pr-4 font-medium">{label}</td>
      <td className="py-2 pr-4 tabular-nums">{github}</td>
      <td className="py-2 pr-4 tabular-nums">{analysed ?? '—'}</td>
      <td className={`py-2 text-xs ${muted}`}>{note}</td>
    </tr>
  )
}

export function RepoNumbers({ repo, overview }: { repo: RepositoryDetail; overview: Overview }) {
  const s = repo.stats
  const c = overview.counts
  const totalIssues = sum(s?.open_issues, s?.closed_issues)
  const totalPrs = sum(s?.open_prs, s?.merged_prs, s?.closed_prs)
  const of = (n: number, total: number | null) => (total === null ? `${fmt(n)}` : `${fmt(n)} of ${fmt(total)}`)
  const sampled = (n: number, total: number | null) => total !== null && n < total

  let discussionsGithub = '—'
  let discussionsNote = ''
  if (s) {
    if (!s.discussions_enabled) {
      discussionsGithub = 'not enabled'
      discussionsNote = 'This repository has GitHub Discussions turned off.'
    } else if (s.discussions === null) {
      discussionsGithub = 'enabled'
      discussionsNote = 'Counting and reading Discussions needs a GitHub token.'
    } else {
      discussionsGithub = fmt(s.discussions)
    }
  }

  return (
    <div className="space-y-3">
      {overview.sync.authenticated === false && (
        <div role="alert" className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-800 dark:text-amber-300">
          The last sync ran <strong>without a GitHub token</strong> (GitHub allows 60 requests per hour), so only a small
          sample of recent activity was analysed and Discussions were skipped. With a server-side token, press
          <strong> Full</strong> in Sync status to analyse much more.
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className={`text-left text-xs ${muted}`}>
            <tr>
              <th className="pb-2 pr-4 font-medium" />
              <th className="pb-2 pr-4 font-medium">On GitHub</th>
              <th className="pb-2 pr-4 font-medium">Analysed by DeciTrace</th>
              <th className="pb-2 font-medium" />
            </tr>
          </thead>
          <tbody>
            <Row label="Issues" github={s ? `${fmt(s.open_issues)} open · ${fmt(s.closed_issues)} closed` : '—'}
              analysed={of(c.issues, totalIssues)} note={sampled(c.issues, totalIssues) ? 'most recently active' : undefined} />
            <Row label="Pull requests" github={s ? `${fmt(s.open_prs)} open · ${fmt(s.merged_prs)} merged · ${fmt(s.closed_prs)} closed` : '—'}
              analysed={of(c.pull_requests, totalPrs)} note={sampled(c.pull_requests, totalPrs) ? 'most recently active' : undefined} />
            <Row label="Discussions" github={discussionsGithub}
              analysed={s?.discussions_enabled ? of(c.discussions, s.discussions) : undefined} note={discussionsNote} />
            <Row label="Comments & reviews" github="—" analysed={fmt(c.comments)} note="on the analysed issues, pull requests and discussions" />
            <Row label="Commits" github={fmt(s?.commits)} analysed={of(c.commits, s?.commits ?? null)}
              note={sampled(c.commits, s?.commits ?? null) ? `most recent, on ${repo.default_branch}` : undefined} />
            <Row label="Files" github="—" analysed={fmt(c.source_files)} note="decision documents, README and key source files" />
            <Row label="Stars · forks" github={`${fmt(s?.stars ?? repo.stars)} · ${fmt(s?.forks)}`} />
          </tbody>
        </table>
      </div>
      <p className={`text-xs ${muted}`}>
        {s ? <>GitHub totals as of {new Date(s.fetched_at).toLocaleString()}.</> : <>GitHub totals appear after the next sync.</>}{' '}
        DeciTrace analyses recent activity rather than the full history, so “analysed” is a sample, not a copy.{' '}
        <ExternalLink href={repo.html_url}>Open on GitHub</ExternalLink>
      </p>
      {overview.top_threads.length > 0 && (
        <div className="pt-2">
          <p className="mb-1 text-sm font-medium">Most-discussed threads collected</p>
          <ul className="space-y-1 text-sm">
            {overview.top_threads.map((t) => (
              <li key={`${t.kind}${t.number}`} className="flex flex-wrap items-baseline gap-2">
                <ExternalLink href={t.url}>{t.kind === 'pull_request' ? 'PR' : t.kind === 'discussion' ? 'Discussion' : 'Issue'} #{t.number}</ExternalLink>
                <span className={`min-w-0 flex-1 truncate ${t.title ? '' : muted}`}>{t.title ?? 'older thread: comments collected, title not collected'}</span>
                <span className={`text-xs ${muted}`}>{t.comments} comments</span>
                {t.analysed ? <Badge color="green">read by extraction</Badge> : <Badge>not yet read</Badge>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
