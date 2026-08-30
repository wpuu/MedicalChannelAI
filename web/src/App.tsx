import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { ToastProvider } from '@/context/ToastContext'
import { AppLayout } from '@/components/layout/AppLayout'
import { FollowedPage } from '@/pages/FollowedPage'
import { LoginPage } from '@/pages/LoginPage'
import { ProfilePage } from '@/pages/ProfilePage'
import { TodayPage } from '@/pages/TodayPage'
import { OpportunityDetailPage } from '@/pages/OpportunityDetailPage'

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<AppLayout />}>
            <Route path="/" element={<Navigate to="/today" replace />} />
            <Route path="/today" element={<TodayPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/followed" element={<FollowedPage />} />
            <Route path="/opportunity/:id" element={<OpportunityDetailPage />} />
            <Route path="*" element={<Navigate to="/today" replace />} />
          </Route>
        </Routes>
      </ToastProvider>
    </BrowserRouter>
  )
}
