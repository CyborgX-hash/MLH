export type JobStatus = 'queued' | 'running' | 'completed' | 'partial' | 'failed'
export type StageStatus = 'pending' | 'running' | 'done' | 'skipped' | 'failed'

export interface StageProgress {
  status: StageStatus
  message?: string
  skipped?: string
  fetched?: number
  truncated?: boolean
  [key: string]: unknown
}

export interface SyncJob {
  id: number
  status: JobStatus
  stage: string
  stage_label: string
  full: boolean
  progress: Record<string, StageProgress | unknown>
  errors: { stage: string; error: string; message: string }[]
  created_at: string
  started_at: string | null
  finished_at: string | null
}

/** Totals as GitHub reports them, fetched during the last sync. Null fields could not be counted. */
export interface RepoStats {
  open_issues: number | null
  closed_issues: number | null
  open_prs: number | null
  merged_prs: number | null
  closed_prs: number | null
  commits: number | null
  discussions: number | null
  discussions_enabled: boolean
  stars: number | null
  forks: number | null
  source: 'graphql' | 'rest'
  fetched_at: string
}

export interface Repository {
  id: number
  owner: string
  name: string
  full_name: string
  html_url: string
  description: string | null
  default_branch: string
  language: string | null
  license_spdx: string | null
  stars: number
  archived: boolean
  has_discussions: boolean
  connected_at: string
  last_synced_at: string | null
  latest_job: SyncJob | null
  stats: RepoStats | null
}

export interface RepositoryDetail extends Repository {
  counts: {
    issues: number
    pull_requests: number
    comments: number
    discussions: number
    commits: number
    source_files: number
  }
}
