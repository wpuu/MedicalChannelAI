import { useEffect, useState } from 'react'
import { Navigate, Outlet } from 'react-router-dom'
import {
  consumeRecentlyAuthenticatedPilotUser,
  getPilotSession,
  isApiMode,
  isAuthRequiredError,
  PILOT_SESSION_CHANGE_KEY,
  type PilotUser,
} from '@/services/apiConfig'
import { activateDiscoveryWorkspaceForAccount } from '@/services/discoveryWorkspaceAccountIsolation'

type State = 'loading' | 'authorized' | 'unauthorized' | 'error'

export function RequirePilotSession() {
  const [state, setState] = useState<State>(isApiMode ? 'loading' : 'authorized')

  useEffect(() => {
    if (!isApiMode) return
    let active = true

    const authorize = async (user: PilotUser) => {
      await activateDiscoveryWorkspaceForAccount(user.local_scope)
      if (active) setState('authorized')
    }

    const recentUser = consumeRecentlyAuthenticatedPilotUser()
    const session = recentUser ? Promise.resolve(recentUser) : getPilotSession()
    void session
      .then(authorize)
      .catch((error) => {
        if (!active) return
        setState(isAuthRequiredError(error) || (error instanceof Error && error.message === 'AUTH_REQUIRED')
          ? 'unauthorized'
          : 'error')
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!isApiMode || typeof window === 'undefined') return
    const handleStorage = (event: StorageEvent) => {
      if (event.key !== PILOT_SESSION_CHANGE_KEY) return
      window.location.reload()
    }
    window.addEventListener('storage', handleStorage)
    return () => window.removeEventListener('storage', handleStorage)
  }, [])

  if (state === 'unauthorized') return <Navigate to="/login" replace />
  if (state === 'authorized') return <Outlet />
  if (state === 'error') {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#f3f5f7] px-4">
        <section className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 text-center shadow-sm">
          <h1 className="text-base font-semibold text-slate-900">账号服务暂时不可用</h1>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            无法确认当前登录状态或安全隔离本机私有工作区。为避免把私有数据错误地加载到其他账号，系统不会降级为匿名模式。
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-4 rounded-xl bg-teal-700 px-4 py-2 text-sm font-medium text-white hover:bg-teal-800"
          >
            重试
          </button>
        </section>
      </main>
    )
  }
  return (
    <main className="flex min-h-screen items-center justify-center bg-[#f3f5f7] px-4 text-sm text-slate-500">
      正在确认账号…
    </main>
  )
}
