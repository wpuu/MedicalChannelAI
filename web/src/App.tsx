import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { RequirePilotSession } from '@/components/auth/RequirePilotSession'
import { AppLayout } from '@/components/layout/AppLayout'
import { ToastProvider } from '@/context/ToastContext'
import { isVerifiedPublicDemo } from '@/config/demoDataset'
import { FollowedPage } from '@/pages/FollowedPage'
import { LoginPage } from '@/pages/LoginPage'
import { OpportunityDetailPage } from '@/pages/OpportunityDetailPage'
import { OpportunityPoolPage } from '@/pages/OpportunityPoolPage'
import { ResourcesPage } from '@/pages/ResourcesPage'
import { TodayPage } from '@/pages/TodayPage'
import { isApiMode } from '@/services/apiConfig'

export default function App() {
  const localTrialEnabled = !isApiMode && isVerifiedPublicDemo

  return (
    <BrowserRouter>
      <ToastProvider>
        <Routes>
          <Route
            path="/login"
            element={isApiMode ? <LoginPage /> : <Navigate to="/today" replace />}
          />
          <Route element={<RequirePilotSession />}>
            <Route element={<AppLayout />}>
              <Route path="/" element={<Navigate to="/today" replace />} />
              <Route path="/today" element={<TodayPage />} />
              <Route
                path="/opportunities"
                element={
                  localTrialEnabled ? <OpportunityPoolPage /> : <Navigate to="/today" replace />
                }
              />
              <Route path="/followed" element={<FollowedPage />} />
              <Route
                path="/resources"
                element={localTrialEnabled ? <ResourcesPage /> : <Navigate to="/today" replace />}
              />
              <Route path="/opportunity/:id" element={<OpportunityDetailPage />} />
              <Route path="*" element={<Navigate to="/today" replace />} />
            </Route>
          </Route>
        </Routes>
      </ToastProvider>
    </BrowserRouter>
  )
}
