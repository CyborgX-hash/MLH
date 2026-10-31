export interface DatabaseHealth {
  reachable: boolean
  pgvector: boolean
  error: string | null
}

export interface Health {
  status: 'ok' | 'degraded'
  app: string
  version: string
  environment: string
  database: DatabaseHealth
  github_token_configured: boolean
}
