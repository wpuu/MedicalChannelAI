import { Link, Outlet, useLocation } from 'react-router-dom';
import { Stethoscope } from 'lucide-react';

export function AppShell() {
  const location = useLocation();
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex h-14 w-full max-w-[1240px] items-center justify-between px-4 sm:px-6">
          <Link to="/today" className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-600 text-white">
              <Stethoscope className="h-4 w-4" />
            </span>
            <span className="text-sm font-bold tracking-tight text-slate-900 sm:text-base">医疗商机助手</span>
          </Link>
          <nav className="flex items-center gap-1 text-sm">
            <Link
              to="/today"
              className={`rounded-lg px-3 py-1.5 font-medium ${
                location.pathname.startsWith('/today') ? 'bg-slate-900 text-white' : 'text-slate-500 hover:bg-slate-100'
              }`}
            >
              今日行动
            </Link>
          </nav>
        </div>
      </header>
      <Outlet />
    </div>
  );
}
