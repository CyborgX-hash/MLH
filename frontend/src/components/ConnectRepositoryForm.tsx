import { useState, type FormEvent } from 'react'

import { connectRepository } from '../services/api'
import type { RepositoryDetail } from '../types/repository'

interface Props {
  onConnected: (repo: RepositoryDetail) => void
}

export function ConnectRepositoryForm({ onConnected }: Props) {
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const repo = await connectRepository(url.trim())
      setUrl('')
      onConnected(repo)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not connect the repository.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <label htmlFor="repo-url" className="text-lg font-semibold">
        Connect a public GitHub repository
      </label>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <input
          id="repo-url"
          type="text"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://github.com/psf/requests"
          className="flex-1 rounded-md border border-slate-300 px-3 py-2 focus:border-indigo-500 focus:outline-none"
          disabled={busy}
          required
        />
        <button
          type="submit"
          disabled={busy || !url.trim()}
          className="rounded-md bg-indigo-600 px-4 py-2 font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {busy ? 'Connecting…' : 'Connect'}
        </button>
      </div>
      {error && (
        <p role="alert" className="mt-3 rounded-md bg-rose-50 p-3 text-sm text-rose-800">
          {error}
        </p>
      )}
    </form>
  )
}
