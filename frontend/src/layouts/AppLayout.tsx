import type { ReactNode } from 'react'

export function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-5xl px-4 py-4">
          <h1 className="text-xl font-semibold">DeciTrace</h1>
          <p className="text-sm text-slate-500">
            Don't just understand what the code does. Understand why it was built that way.
          </p>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8">{children}</main>
    </div>
  )
}
