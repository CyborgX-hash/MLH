// Shared class names: one place for the visual language (dark-first, subtle borders, restrained accent).
export const card = 'rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900/60'
export const cardPad = `${card} p-5`
export const muted = 'text-zinc-500 dark:text-zinc-400'
export const subtle = 'text-zinc-400 dark:text-zinc-500'
export const heading = 'text-lg font-semibold tracking-tight'
export const input =
  'w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm placeholder:text-zinc-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 dark:border-zinc-700 dark:bg-zinc-900 dark:placeholder:text-zinc-500'
export const btn =
  'inline-flex items-center justify-center gap-2 rounded-lg border border-zinc-300 px-3 py-1.5 text-sm font-medium hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-800'
export const btnPrimary =
  'inline-flex items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50'
export const link = 'text-indigo-600 hover:underline dark:text-indigo-400'
export const pill = 'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset'

export const tone = {
  green: 'bg-emerald-500/10 text-emerald-700 ring-emerald-500/25 dark:text-emerald-300',
  amber: 'bg-amber-500/10 text-amber-800 ring-amber-500/25 dark:text-amber-300',
  red: 'bg-rose-500/10 text-rose-700 ring-rose-500/25 dark:text-rose-300',
  blue: 'bg-indigo-500/10 text-indigo-700 ring-indigo-500/25 dark:text-indigo-300',
  gray: 'bg-zinc-500/10 text-zinc-700 ring-zinc-500/25 dark:text-zinc-300',
}
