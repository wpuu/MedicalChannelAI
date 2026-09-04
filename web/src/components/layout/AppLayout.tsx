import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import {
  Activity,
  BookmarkCheck,
  BriefcaseBusiness,
  ClipboardList,
  LogOut,
  Radar,
  RotateCcw,
  Target,
} from 'lucide-react'
import { APP_BUILD_LABEL } from '@/config/appVersion'
import { isVerifiedPublicDemo } from '@/config/demoDataset'
import { useToast } from '@/context/ToastContext'
import { isApiMode, logoutPilot } from '@/services/apiConfig'
import { clearLocalCustomerProfile } from '@/services/localCustomerProfile'
import { resetLocalFollowups } from '@/services/localFollowupStore'
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

  const desktopNavClass = ({ isActive }: { isActive: boolean }) =>
    cn(
      'rounded-lg px-3 py-1.5 text-[13px] font-medium',
      isActive ? 'bg-teal-700 text-white' : 'text-slate-600 hover:bg-slate-100',
    )

  const mobileNavClass = ({ isActive }: { isActive: boolean }) =>
    cn(
      'flex min-w-0 flex-1 flex-col items-center justify-center gap-0.5 rounded-xl px-1 py-1.5 text-[10px] font-medium',
      isActive ? 'bg-teal-50 text-teal-800' : 'text-slate-500',
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

  const handleResetTrial = async () => {
    // Mock reset is a demo-only action. Keep the synthetic service out of the
    // authenticated Pilot shell and load it only when the user actually resets.
    const { resetMockDemoState } = await import('@/services/MockTodayActionsService')
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
    ? '天津试用'
    : isVerifiedPublicDemo
      ? '天津公开试用'
      : '演示数据'

  const showPool = !isApiMode && isVerifiedPublicDemo
  const showResources = isApiMode || isVerifiedPublicDemo
  const showTargets = isApiMode || isVerifiedPublicDemo

  return (
    <div className="min-h-screen bg-[#f3f5f7]">
      <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[1200px] items-center justify-between gap-3 px-3 sm:h-auto sm:px-4 sm:py-3">
          <div className="flex min-w-0 items-center gap-2.5">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-teal-700 text-white sm:h-8 sm:w-8 sm:rounded-lg">
              <Activity className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h1 className="truncate text-[16px] font-semibold text-slate-900 sm:text-[15px]">
                  医疗商机助手
                </h1>
                <span
                  className={cn(
                    'hidden shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-medium ring-1 lg:inline-flex',
                    isApiMode || isVerifiedPublicDemo
                      ? 'bg-teal-50 text-teal-800 ring-teal-200'
                      : 'bg-amber-50 text-amber-800 ring-amber-200',
                  )}
                >
                  {modeLabel}
                </span>
              </div>
            </div>
          </div>

          <nav className="hidden shrink-0 items-center gap-1 sm:flex">
            <NavLink to="/radar" className={desktopNavClass}>AI雷达</NavLink>
            <NavLink to="/today" className={desktopNavClass}>今日行动</NavLink>
            {showTargets ? <NavLink to="/targets" className={desktopNavClass}>目标医院</NavLink> : null}
            {showPool ? <NavLink to="/opportunities" className={desktopNavClass}>商机池</NavLink> : null}
            <NavLink to="/followed" className={desktopNavClass}>我的跟进</NavLink>
            {showResources ? <NavLink to="/resources" className={desktopNavClass}>我的资源</NavLink> : null}
          </nav>

          <div className="flex shrink-0 items-center gap-1">
            {!isApiMode ? (
              <button
                type="button"
                onClick={() => void handleResetTrial()}
                title={isVerifiedPublicDemo ? '清除本机试用状态' : '恢复演示初始状态'}
                aria-label={isVerifiedPublicDemo ? '清除本机试用状态' : '恢复演示初始状态'}
                className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-800 sm:h-auto sm:w-auto sm:gap-1 sm:px-2.5 sm:py-1.5 sm:text-[12px]"
              >
                <RotateCcw className="h-4 w-4 sm:h-3.5 sm:w-3.5" />
                <span className="hidden lg:inline">{isVerifiedPublicDemo ? '重置试用' : '重置演示'}</span>
              </button>
            ) : null}
            {isApiMode ? (
              <button
                type="button"
                disabled={loggingOut}
                onClick={() => void handleLogout()}
                className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-800 disabled:opacity-50 sm:h-auto sm:w-auto sm:gap-1 sm:px-2.5 sm:py-1.5 sm:text-[12px]"
              >
                <LogOut className="h-4 w-4 sm:h-3.5 sm:w-3.5" />
                <span className="hidden sm:inline">退出</span>
              </button>
            ) : null}
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1200px] px-3 py-3 pb-28 sm:px-4 sm:py-6 sm:pb-16">
        <Outlet />
      </main>

      <nav className="fixed inset-x-0 bottom-0 z-50 border-t border-slate-200 bg-white/95 px-2 pt-1.5 pb-[calc(env(safe-area-inset-bottom)+0.45rem)] shadow-[0_-8px_24px_rgba(15,23,42,0.06)] backdrop-blur sm:hidden">
        <div className="mx-auto flex max-w-md gap-1">
          <NavLink to="/radar" className={mobileNavClass}>
            <Radar className="h-5 w-5" />
            <span>雷达</span>
          </NavLink>
          <NavLink to="/today" className={mobileNavClass}>
            <ClipboardList className="h-5 w-5" />
            <span>今日</span>
          </NavLink>
          {showTargets ? (
            <NavLink to="/targets" className={mobileNavClass}>
              <Target className="h-5 w-5" />
              <span>目标</span>
            </NavLink>
          ) : null}
          <NavLink to="/followed" className={mobileNavClass}>
            <BookmarkCheck className="h-5 w-5" />
            <span>跟进</span>
          </NavLink>
          {showResources ? (
            <NavLink to="/resources" className={mobileNavClass}>
              <BriefcaseBusiness className="h-5 w-5" />
              <span>资源</span>
            </NavLink>
          ) : null}
        </div>
      </nav>

      <div
        className="fixed bottom-1 right-2 z-30 hidden select-none rounded bg-white/80 px-1.5 py-0.5 text-[10px] text-slate-400 shadow-sm ring-1 ring-slate-200/70 backdrop-blur sm:block"
        title="当前页面版本与构建提交"
      >
        {APP_BUILD_LABEL}
      </div>
    </div>
  )
}
