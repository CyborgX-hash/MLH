import { Link, NavLink, Outlet } from 'react-router-dom'

import { Logo } from '../components/ui'
import { useTheme } from '../lib/theme'
import { muted } from '../lib/ui'

export function AppShell() {
  const { theme, toggle } = useTheme()
  const nav = ({ isActive }: { isActive: boolean }) =>
    `rounded-md px-2.5 py-1.5 text-sm ${isActive ? 'bg-zinc-200/70 font-medium dark:bg-zinc-800' : `${muted} hover:text-zinc-900 dark:hover:text-zinc-100`}`

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-zinc-200 bg-zinc-50/80 backdrop-blur dark:border-zinc-800 dark:bg-zinc-950/80">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-3">
          <Link to="/" className="flex items-center gap-2 font-semibold tracking-tight">
            <Logo />
            DeciTrace
          </Link>
          <nav className="ml-2 flex items-center gap-1">
            <NavLink to="/connect" className={nav}>
              Repositories
            </NavLink>
          </nav>
          <button
            onClick={toggle}
            className={`ml-auto rounded-md px-2.5 py-1.5 text-sm ${muted} hover:text-zinc-900 dark:hover:text-zinc-100`}
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
          >
            {theme === 'dark' ? '☀︎ Light' : '☾ Dark'}
          </button>
        </div>
      </header>
      <Outlet />
    </div>
  )
}
