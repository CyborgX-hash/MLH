import { useCallback, useState } from 'react'

export type Theme = 'dark' | 'light'
const KEY = 'decitrace-theme'

function current(): Theme {
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light'
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(current)
  const toggle = useCallback(() => {
    const next: Theme = current() === 'dark' ? 'light' : 'dark'
    document.documentElement.classList.toggle('dark', next === 'dark')
    try {
      localStorage.setItem(KEY, next)
    } catch {
      // storage unavailable (private mode): the choice lasts for this page only
    }
    setTheme(next)
  }, [])
  return { theme, toggle }
}
