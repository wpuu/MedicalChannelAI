import { NavLink, Outlet } from 'react-router-dom'
import { Activity, CalendarDays } from 'lucide-react'
import { formatToday } from '@/utils/format'
import { cn } from '@/utils/cn'

export function AppLayout() {
  return (
    <div className="min-h-screen bg-[#f3f5f7]">
      <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1200px] items-center justify-between gap-3 px-4 py-3">
          <div className="flex min-w-0 items-center gap-2.5">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-teal-700 text-white">
              <Activity className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h1 className="truncate text-[15px] font-semibold text-slate-900">
                  医疗商机助手
                </h1>
                <span className="shrink-0 rounded-md bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-800 ring-1 ring-amber-200">
                  演示数据
                </span>
              </div>
              <p className="hidden items-center gap-1 text-[11px] text-slate-500 sm:flex">
                <CalendarDays className="h-3 w-3" />
                {formatToday()}
              </p>
            </div>
          </div>
          <nav className="flex items-center gap-1">
            <NavLink
              to="/today"
              className={({ isActive }) =>
                cn(
                  'rounded-lg px-3 py-1.5 text-[13px] font-medium',
                  isActive
                    ? 'bg-teal-700 text-white'
                    : 'text-slate-600 hover:bg-slate-100',
                )
              }
            >
              今日行动
            </NavLink>
          </nav>
        </div>
        <p className="border-t border-slate-100 px-4 py-1.5 text-center text-[11px] text-slate-500 sm:hidden">
          {formatToday()}
        </p>
      </header>
      <main className="mx-auto w-full max-w-[1200px] px-4 py-4 pb-16 sm:py-6">
        <Outlet />
      </main>
    </div>
  )
}
