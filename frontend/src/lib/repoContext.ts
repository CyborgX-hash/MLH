import { useOutletContext } from 'react-router-dom'

import type { RepositoryDetail } from '../types/repository'

export interface RepoContext {
  repo: RepositoryDetail
  reload: () => void
}

/** The repository loaded by RepoLayout, available to every page nested under /repos/:repoId. */
export function useRepo() {
  return useOutletContext<RepoContext>()
}
