import { useCallback, useEffect, useState } from 'react'

import { getRepository } from '../services/api'
import type { RepositoryDetail } from '../types/repository'

const POLL_MS = 1500

/** Loads one repository and keeps polling while its sync job is queued or running. */
export function useRepositoryDetail(id: number) {
  const [repo, setRepo] = useState<RepositoryDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [version, setVersion] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    let timer: number | undefined

    const load = () => {
      getRepository(id, controller.signal)
        .then((data) => {
          setRepo(data)
          setError(null)
          const status = data.latest_job?.status
          if (status === 'queued' || status === 'running') timer = window.setTimeout(load, POLL_MS)
        })
        .catch((err: unknown) => {
          if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'Unknown error')
        })
    }
    load()
    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [id, version])

  const refresh = useCallback(() => setVersion((v) => v + 1), [])
  return { repo, error, refresh }
}
