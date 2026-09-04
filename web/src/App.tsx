import { lazy, Suspense, type ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { RequirePilotSession } from '@/components/auth/RequirePilotSession'
import { AppLayout } from '@/components/layout/AppLayout'
import { LoadingState } from '@/components/shared/PageStates'
import { ToastProvider } from '@/context/ToastContext'
import { isVerifiedPublicDemo } from '@/config/demoDataset'
import { TodayPage } from '@/pages/TodayPage'
import { isApiMode } from '@/services/apiConfig'

const LoginPage = lazy(() =>
  import('@/pages/LoginPage').then((module) => ({ default: module.LoginPage })),
)
const DiscoveryRadarRoute = lazy(() =>
  import('@/pages/DiscoveryRadarRoute').then((module) => ({ default: module.DiscoveryRadarRoute })),
)
const FollowedPage = lazy(() =>
  import('@/pages/FollowedPage').then((module) => ({ default: module.FollowedPage })),
)
const OpportunityDetailPage = lazy(() =>
  import('@/pages/OpportunityDetailPage').then((module) => ({ default: module.OpportunityDetailPage })),
)
const OpportunityPoolPage = lazy(() =>
  import('@/pages/OpportunityPoolPage').then((module) => ({ default: module.OpportunityPoolPage })),
)
const ProcurementIntentFollowupPage = lazy(() =>
  import('@/pages/ProcurementIntentFollowupPage').then((module) => ({
    default: module.ProcurementIntentFollowupPage,
  })),
)
const PilotResourcesPage = lazy(() =>
  import('@/pages/PilotResourcesPage').then((module) => ({ default: module.PilotResourcesPage })),
)
const ResourcesPage = lazy(() =>
  import('@/pages/ResourcesPage').then((module) => ({ default: module.ResourcesPage })),
)
const TargetHospitalsPage = lazy(() =>
  import('@/pages/TargetHospitalsPage').then((module) => ({ default: module.TargetHospitalsPage })),
)

function lazyPage(element: ReactNode) {
  return <Suspense fallback={<LoadingState />}>{element}</Suspense>
}

export default function App() {
  const localTrialEnabled = !isApiMode && isVerifiedPublicDemo
  const authenticatedOrTrial = isApiMode || localTrialEnabled

  return (
    <BrowserRouter>
      <ToastProvider>
        <Routes>
          <Route
            path="/login"
            element={isApiMode ? lazyPage(<LoginPage />) : <Navigate to="/today" replace />}
          />
          <Route element={<RequirePilotSession />}>
            <Route element={<AppLayout />}>
              <Route path="/" element={<Navigate to="/today" replace />} />
              <Route path="/radar" element={lazyPage(<DiscoveryRadarRoute />)} />
              <Route path="/today" element={<TodayPage />} />
              <Route
                path="/targets"
                element={
                  authenticatedOrTrial
                    ? lazyPage(<TargetHospitalsPage />)
                    : <Navigate to="/today" replace />
                }
              />
              <Route
                path="/opportunities"
                element={
                  authenticatedOrTrial
                    ? lazyPage(<OpportunityPoolPage />)
                    : <Navigate to="/today" replace />
                }
              />
              <Route
                path="/intent-followup"
                element={
                  authenticatedOrTrial
                    ? lazyPage(<ProcurementIntentFollowupPage />)
                    : <Navigate to="/today" replace />
                }
              />
              <Route path="/followed" element={lazyPage(<FollowedPage />)} />
              <Route
                path="/resources"
                element={
                  isApiMode
                    ? lazyPage(<PilotResourcesPage />)
                    : localTrialEnabled
                      ? lazyPage(<ResourcesPage />)
                      : <Navigate to="/today" replace />
                }
              />
              <Route path="/opportunity/:id" element={lazyPage(<OpportunityDetailPage />)} />
              <Route path="*" element={<Navigate to="/today" replace />} />
            </Route>
          </Route>
        </Routes>
      </ToastProvider>
    </BrowserRouter>
  )
}
