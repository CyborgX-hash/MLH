import { Link } from 'react-router-dom'

import { Badge, Logo } from '../components/ui'
import { btnPrimary, card, muted } from '../lib/ui'

const STEPS = [
  ['Connect', 'Paste a public GitHub repository URL. No question needed yet.'],
  ['Collect', 'Issues, pull requests, reviews, discussions, commits and key files are ingested and linked.'],
  ['Validate', 'Extracted decisions are kept only when real comments support them. Disagreements stay unresolved.'],
  ['Ask', 'Ask why something was built a certain way and get an answer with GitHub citations.'],
]

const FEATURES = [
  ['Evidence, not guesses', 'Every claim points to the original comment, issue, PR or commit. Unsupported claims are flagged, not hidden.'],
  ['Conflicts stay visible', 'When developers disagree and no maintainer settled it, DeciTrace says so instead of picking a winner.'],
  ['Rejected alternatives', 'See what was tried or proposed, and why it was rejected, when the reason was actually recorded.'],
  ['Decision to code', 'Follow a decision to the PRs and files that implemented it, through renames and deletions.'],
  ['Human review', 'Maintainers with write access can confirm outcomes. Every change is audited.'],
  ['Open models', 'Runs on open-weight models through any OpenAI-compatible endpoint, locally with Ollama.'],
]

// Illustrative only: shown on the landing page to explain the idea, never mixed with repository data.
const EXAMPLE = [
  ['Issue #12', 'Proposal', 'MongoDB proposed for order storage.'],
  ['Discussion #8', 'Argument', 'PostgreSQL suggested for multi-document transactions.'],
  ['Comment by a maintainer', 'Approval', '"We decided to go with PostgreSQL."'],
  ['PR #25', 'Implementation', 'Closes #12; changes src/db.py, later renamed to storage/db.py.'],
]

export function LandingPage() {
  return (
    <div className="mx-auto max-w-6xl px-4 pb-24">
      <section className="pt-20 pb-16 text-center">
        <div className="mx-auto mb-6 w-fit"><Logo size={48} /></div>
        <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">DeciTrace</h1>
        <p className="mx-auto mt-4 max-w-2xl text-lg text-zinc-600 dark:text-zinc-300">
          Don't just understand what the code does. Understand why it was built that way.
        </p>
        <div className="mt-8 flex justify-center gap-3">
          <Link to="/connect" className={btnPrimary}>Connect a repository</Link>
        </div>
      </section>

      <section className={`${card} p-6 sm:p-8`}>
        <h2 className="text-lg font-semibold">The problem</h2>
        <p className={`mt-2 max-w-3xl ${muted}`}>
          Important engineering decisions are made in issue threads, review comments and discussions, then buried once
          the thread closes. New contributors re-propose ideas that were already rejected, and the reasons behind the
          code leave with the people who wrote it. DeciTrace recovers that history from the repository itself and keeps
          every conclusion tied to its source.
        </p>
      </section>

      <section className="mt-16">
        <h2 className="text-lg font-semibold">How it works</h2>
        <ol className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map(([title, text], i) => (
            <li key={title} className={`${card} p-5`}>
              <span className="text-xs font-semibold text-indigo-600 dark:text-indigo-400">0{i + 1}</span>
              <p className="mt-1 font-medium">{title}</p>
              <p className={`mt-1 text-sm ${muted}`}>{text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="mt-16">
        <h2 className="text-lg font-semibold">Core features</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(([title, text]) => (
            <div key={title} className={`${card} p-5`}>
              <p className="font-medium">{title}</p>
              <p className={`mt-1 text-sm ${muted}`}>{text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="mt-16">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold">Example decision history</h2>
          <Badge color="amber">Illustrative example, not real repository data</Badge>
        </div>
        <ol className={`${card} mt-4 divide-y divide-zinc-200 dark:divide-zinc-800`}>
          {EXAMPLE.map(([source, kind, text]) => (
            <li key={source} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 px-5 py-3 text-sm">
              <span className="w-28 shrink-0 font-medium">{kind}</span>
              <span className={`w-48 shrink-0 ${muted}`}>{source}</span>
              <span>{text}</span>
            </li>
          ))}
        </ol>
      </section>

      <section className="mt-16 text-center">
        <Link to="/connect" className={btnPrimary}>Connect a repository</Link>
      </section>
    </div>
  )
}
