import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { Activity, CalendarDays, LogOut, RotateCcw } from 'lucide-react'
import { APP_BUILD_LABEL } from '@/config/appVersion'
import { isVerifiedPublicDemo } from '@/config/demoDataset'
import { useToast } from '@/context/ToastContext'
import { isApiMode, logoutPilot } from '@/services/apiConfig'
import { clearLocalCustomerProfile } from '@/services/localCustomerProfile'
import { resetLocalFollowups } from '@/services/localFollowupStore'
import { resetMockDemoState } from '@/services/MockTodayActionsService'
import { formatToday } from '@/utils/format'
import { cn } from '@/utils/cn'

const GROUNDED_AI_CACHE_KEY = 'medopp.grounded-ai-decisions.v1'
const AI_DECISION_CONTRACT_KEY = 'medopp.ai-decision-contract-version'
const AI_DECISION_CONTRACT_VERSION = 'v2'

function migrateAiDecisionCacheContract(): void {
  if (typeof localStorage === 'undefined') return
  try {
    if (localStorage.getItem(AI_DECISION_CONTRACT_KEY) === AI_DECISION_CONTRACT_VERSION) return
    localStorage.removeItem(GROUNDED_AI_CACHE_KEY)
    localStorage.setItem(AI_DECISION_CONTRACT_KEY, AI_DECISION_CONTRACT_VERSION)
  } catch {
    // Cache migration is best-effort; AI analysis can run without local storage.
  }
}

migrateAiDecisionCacheContract()

export function AppLayout() {
  const navigate = useNavigate()
  const { toast } = useToast()
  const [loggingOut, setLoggingOut] = useState(false)

  const navClass = ({ isActive }: { isActive: boolean }) =>
    cn(
      'rounded-lg px-2.5 py-1.5 text-[13px] font-medium sm:px-3',
      isActive
        ? 'bg-teal-700 text-white'
        : 'text-slate-600 hover:bg-slate-100',
    )

  const handleLogout = async () => {
    setLoggingOut(true)
    try {
      await logoutPilot()
      navigate('/login', { replace: true })
    } catch {
      toast('退出失败，请检查网络后重试')
    } finally {
      setLoggingOut(false)
    }
  }

  const handleResetTrial = () => {
    resetMockDemoState()
    resetLocalFollowups()
    if (isVerifiedPublicDemo) clearLocalCustomerProfile()
    try {
      localStorage.removeItem(GROUNDED_AI_CACHE_KEY)
    } catch {
      // Storage reset is best-effort; reload still resets in-memory state.
    }
    window.location.assign('/today')
  }

  const modeLabel = isApiMode
    ? '天津 Pilot'
    : isVerifiedPublicDemo
      ? '真实公开试用'
      : '演示数据'

  return (
    <div className="min-h-screen bg-[#f3f5f7]">
      <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1200px] items-center justify-between gap-2 px-3 py-3 sm:gap-3 sm:px-4">
          <div className="flex min-w-0 items-center gap-2.5">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-teal-700 text-white">
              <Activity className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h1 className="hidden truncate text-[15px] font-semibold text-slate-900 min-[390px]:block">
                  医疗商机助手
                </h1>
                <span
                  className={cn(
                    'shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-medium ring-1',
                    isApiMode || isVerifiedPublicDemo
                      ? 'bg-teal-50 text-teal-800 ring-teal-200'
                      : 'bg-amber-50 text-amber-800 ring-amber-200',
                  )}
                >
                  {modeLabel}
                </span>
              </div>
              <p className="hidden items-center gap-1 text-[11px] text-slate-500 md:flex">
                <CalendarDays className="h-3 w-3" />
                {formatToday()}
              </p>
            </div>
          </div>
          <nav className="flex shrink-0 items-center gap-0.5 sm:gap-1">
            <NavLink to="/today" className={navClass}>
              今日行动
            </NavLink>
            {!isApiMode && isVerifiedPublicDemo ? (
              <NavLink to="/opportunities" className={navClass}>
                商机池
              </NavLink>
            ) : null}
            <NavLink to="/followed" className={navClass}>
              我的跟进
            </NavLink>
            {!isApiMode && isVerifiedPublicDemo ? (
              <NavLink to="/resources" className={navClass}>
                我的资源
              </NavLink>
            ) : null}
            {!isApiMode ? (
              <button
                type="button"
                onClick={handleResetTrial}
                title={isVerifiedPublicDemo ? '清除本地试用状态' : '恢复演示初始状态'}
                className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-[12px] text-slate-500 hover:bg-slate-100 hover:text-slate-800 sm:px-2.5"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                <span className="hidden md:inline">
                  {isVerifiedPublicDemo ? '重置试用' : '重置演示'}
                </span>
              </button>
            ) : null}
            {isApiMode ? (
              <button
                type="button"
                disabled={loggingOut}
                onClick={() => void handleLogout()}
                className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-[12px] text-slate-500 hover:bg-slate-100 hover:text-slate-800 disabled:opacity-50 sm:px-2.5"
              >
                <LogOut className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">退出</span>
              </button>
            ) : null}
          </nav>
        </div>
        <p className="border-t border-slate-100 px-4 py-1.5 text-center text-[11px] text-slate-500 md:hidden">
          {formatToday()}
        </p>
      </header>
      <main className="mx-auto w-full max-w-[1200px] px-4 py-4 pb-16 sm:py-6">
        <Outlet />
      </main>
      <div
        className="fixed bottom-1 right-2 z-30 select-none rounded bg-white/80 px-1.5 py-0.5 text-[10px] text-slate-400 shadow-sm ring-1 ring-slate-200/70 backdrop-blur"
        title="当前页面版本与构建提交"
      >
        {APP_BUILD_LABEL}
      </div>
    </div>
  )
}
