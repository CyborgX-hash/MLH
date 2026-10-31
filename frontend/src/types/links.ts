export interface RecordRef {
  kind: string
  id: number
}

export interface SourceLink {
  source: RecordRef
  target: RecordRef
  relation: string
  signal: string
  verification_status: 'verified' | 'possible'
  confidence: number
  evidence: { snippet?: string; url?: string; paths?: string[]; terms?: string[] }
}

export interface RecordInfo {
  kind: string
  id: number
  number: number | null
  title: string | null
  url: string | null
  state: string | null
  sha: string | null
  cited: boolean
  missing: boolean
}

export interface RelatedGraph {
  records: RecordInfo[]
  links: SourceLink[]
}

export interface CodeLink {
  link_status: 'verified' | 'possible'
  basis: string
  pr_number: number | null
  pr_url: string | null
  merged_at: string | null
  commit_sha: string | null
  commit_url: string | null
  path: string | null
  change_type: string | null
  current_path: string | null
  deleted: boolean
  changed_after: number[]
}

export interface CodeMap {
  decision_id: number
  message: string | null
  verified: CodeLink[]
  possible: CodeLink[]
  notes: string[]
}
