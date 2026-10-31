import { Link, Route, Routes } from 'react-router-dom'

import { AppShell } from './layouts/AppShell'
import { RepoLayout } from './layouts/RepoLayout'
import { AskPage } from './pages/AskPage'
import { ConflictReviewPage } from './pages/ConflictReviewPage'
import { ConnectPage } from './pages/ConnectPage'
import { DashboardPage } from './pages/DashboardPage'
import { DecisionDetailPage } from './pages/DecisionDetailPage'
import { DecisionExplorerPage } from './pages/DecisionExplorerPage'
import { LandingPage } from './pages/LandingPage'
import { PrImpactPage } from './pages/PrImpactPage'

function NotFound() {
  return (
    <div className="mx-auto max-w-7xl p-8">
      <p className="text-lg font-semibold">Page not found</p>
      <Link to="/" className="text-indigo-600 hover:underline dark:text-indigo-400">Back to DeciTrace</Link>
    </div>
  )
}

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<LandingPage />} />
        <Route path="connect" element={<ConnectPage />} />
        <Route path="repos/:repoId" element={<RepoLayout />}>
          <Route index element={<DashboardPage />} />
          <Route path="decisions" element={<DecisionExplorerPage />} />
          <Route path="decisions/:decisionId" element={<DecisionDetailPage />} />
          <Route path="ask" element={<AskPage />} />
          <Route path="conflicts" element={<ConflictReviewPage />} />
          <Route path="pr-impact" element={<PrImpactPage />} />
        </Route>
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
