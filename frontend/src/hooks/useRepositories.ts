import { useCallback, useEffect, useState } from 'react'

import { listRepositories } from '../services/api'
import type { Repository } from '../types/repository'

export function useRepositories() {
  const [repos, setRepos] = useState<Repository[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [version, setVersion] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    listRepositories(controller.signal)
      .then((data) => {
        setRepos(data)
        setError(null)
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'Unknown error')
      })
    return () => controller.abort()
  }, [version])

  const refresh = useCallback(() => setVersion((v) => v + 1), [])
  return { repos, error, refresh }
}
