import { useCallback, useEffect, useState } from 'react'

import { getHealth } from '../services/api'
import type { Health } from '../types/health'

type State =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; health: Health }

export function useHealth() {
  const [state, setState] = useState<State>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    getHealth(controller.signal)
      .then((health) => setState({ kind: 'ready', health }))
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        setState({ kind: 'error', message: err instanceof Error ? err.message : 'Unknown error' })
      })
    return () => controller.abort()
  }, [attempt])

  const retry = useCallback(() => {
    setState({ kind: 'loading' })
    setAttempt((n) => n + 1)
  }, [])
  return { state, retry }
}
