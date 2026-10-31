import type { ReactNode } from 'react'

import { isSafeGithubUrl } from '../lib/safeUrl'
import { card, muted, pill, tone } from '../lib/ui'

export function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="7" className="fill-zinc-900 dark:fill-zinc-800" />
      <circle cx="9" cy="10" r="3" className="fill-indigo-300" />
      <circle cx="9" cy="22" r="3" className="fill-zinc-500" />
      <circle cx="23" cy="16" r="3.5" className="fill-indigo-300" />
      <path d="M11.5 11.2 19.8 15M11.5 20.8l8.3-3.8" className="stroke-indigo-300" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

export function Badge({ children, color = 'gray' }: { children: ReactNode; color?: keyof typeof tone }) {
  return <span className={`${pill} ${tone[color]}`}>{children}</span>
}

export function Spinner({ label = 'Loading…' }: { label?: string }) {
  return (
    <p className={`flex items-center gap-2 text-sm ${muted}`} role="status">
      <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-zinc-400 border-t-transparent" aria-hidden />
      {label}
    </p>
  )
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-center gap-3 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-700 dark:text-rose-300">
      <span>{message}</span>
      {onRetry && (
        <button onClick={onRetry} className="rounded-md bg-rose-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-rose-500">
          Retry
        </button>
      )}
    </div>
  )
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className={`${card} border-dashed p-8 text-center`}>
      <p className="font-medium">{title}</p>
      {children && <div className={`mt-1 text-sm ${muted}`}>{children}</div>}
    </div>
  )
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className={`${card} p-4`}>
      <p className={`text-xs ${muted}`}>{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {hint && <p className={`mt-0.5 text-xs ${muted}`}>{hint}</p>}
    </div>
  )
}

export function Section({ title, children, aside }: { title: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  )
}

export function ExternalLink({ href, children, className = '' }: { href: string; children: ReactNode; className?: string }) {
  if (!isSafeGithubUrl(href)) return <span className={className}>{children}</span>
  return (
    <a href={href} target="_blank" rel="noreferrer" className={`text-indigo-600 hover:underline dark:text-indigo-400 ${className}`}>
      {children}
    </a>
  )
}
