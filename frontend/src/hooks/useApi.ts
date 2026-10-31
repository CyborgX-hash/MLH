import { useCallback, useEffect, useState } from 'react'

interface State<T> {
  data: T | null
  error: string | null
  loading: boolean
}

/**
 * Load data from the API with loading/error state and abort on unmount.
 * `pollWhile(data)` keeps re-fetching every `pollMs` while it returns true.
 */
export function useApi<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  deps: unknown[],
  opts: { pollWhile?: (data: T) => boolean; pollMs?: number } = {},
) {
  const [state, setState] = useState<State<T>>({ data: null, error: null, loading: true })
  const [version, setVersion] = useState(0)
  const { pollWhile, pollMs = 1500 } = opts

  useEffect(() => {
    const controller = new AbortController()
    let timer: number | undefined
    const load = () => {
      fetcher(controller.signal)
        .then((data) => {
          setState({ data, error: null, loading: false })
          if (pollWhile?.(data)) timer = window.setTimeout(load, pollMs)
        })
        .catch((err: unknown) => {
          if (controller.signal.aborted) return
          setState((s) => ({ ...s, error: err instanceof Error ? err.message : 'Unknown error', loading: false }))
        })
    }
    load()
    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, version])

  const reload = useCallback(() => setVersion((v) => v + 1), [])
  return { ...state, reload }
}
