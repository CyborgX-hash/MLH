import { API_BASE_URL } from '../lib/env'
import type { Decision, DecisionListItem, ReviewRequest } from '../types/decision'
import type { AskResponse, DecisionGraphData, ExtractionJob, ImpactReport, Overview, TimelineEvent } from '../types/views'
import type { Health } from '../types/health'
import type { CodeMap, RelatedGraph } from '../types/links'
import type { Repository, RepositoryDetail, SyncJob } from '../types/repository'

const UNREACHABLE = 'Cannot reach the DeciTrace backend. Is it running on port 8000?'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function send(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(`${API_BASE_URL}${path}`, init)
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new ApiError(UNREACHABLE, 0)
  }
}

// FastAPI errors are {"detail": "..."} or, for validation errors, {"detail": [{msg: ...}]}.
function errorMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg)
  if (status === 502 || status === 504) return UNREACHABLE
  return `Request failed (${status})`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await send(path, init)
  const body = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(errorMessage(body, res.status), res.status)
  return body as T
}

// The health endpoint answers 503 with a JSON body when the database is down,
// so any response carrying a Health payload is returned, not thrown.
export async function getHealth(signal?: AbortSignal): Promise<Health> {
  const res = await send('/api/health', { signal })
  const body = await res.json().catch(() => null)
  if (body && typeof body === 'object' && 'database' in body) return body as Health
  throw new ApiError(errorMessage(body, res.status), res.status)
}

const json = (data: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(data),
})

export const connectRepository = (url: string) => request<RepositoryDetail>('/api/repositories/connect', json({ url }))
export const listRepositories = (signal?: AbortSignal) => request<Repository[]>('/api/repositories', { signal })
export const getRepository = (id: number, signal?: AbortSignal) =>
  request<RepositoryDetail>(`/api/repositories/${id}`, { signal })
export const listDecisions = (repoId: number, signal?: AbortSignal) =>
  request<DecisionListItem[]>(`/api/repositories/${repoId}/decisions`, { signal })
export const getOverview = (repoId: number, signal?: AbortSignal) =>
  request<Overview>(`/api/repositories/${repoId}/overview`, { signal })
export const getTimeline = (decisionId: number, signal?: AbortSignal) =>
  request<TimelineEvent[]>(`/api/decisions/${decisionId}/timeline`, { signal })
export const getGraph = (decisionId: number, signal?: AbortSignal) =>
  request<DecisionGraphData>(`/api/decisions/${decisionId}/graph`, { signal })
export const startExtraction = (repoId: number, limit = 5) =>
  request<ExtractionJob>(`/api/repositories/${repoId}/extract?limit=${limit}`, { method: 'POST' })
export const getExtractionStatus = (repoId: number, signal?: AbortSignal) =>
  request<ExtractionJob | null>(`/api/repositories/${repoId}/extraction-status`, { signal })
export const analyzePullRequest =(prUrl: string) => request<ImpactReport>('/api/pr-impact', json({ pr_url: prUrl }))
export const askQuestion =(repoId: number, question: string, signal?: AbortSignal) =>
  request<AskResponse>(`/api/repositories/${repoId}/ask`, { ...json({ question }), signal })
export const getDecision = (id: number, signal?: AbortSignal) => request<Decision>(`/api/decisions/${id}`, { signal })
// The reviewer's own GitHub token proves identity and repository access. It is sent once and never stored.
export const reviewDecision = (id: number, body: ReviewRequest, githubToken: string) =>
  request<Decision>(`/api/decisions/${id}/reviews`, {
    ...json(body),
    headers: { 'Content-Type': 'application/json', 'X-GitHub-Token': githubToken },
  })
export const getRelated = (decisionId: number, signal?: AbortSignal) =>
  request<RelatedGraph>(`/api/decisions/${decisionId}/related`, { signal })
export const getCodeMap = (decisionId: number, signal?: AbortSignal) =>
  request<CodeMap>(`/api/decisions/${decisionId}/code`, { signal })
export const syncRepository = (id: number, full = false) =>
  request<SyncJob>(`/api/repositories/${id}/sync?full=${full}`, { method: 'POST' })
