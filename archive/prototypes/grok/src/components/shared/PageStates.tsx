import { AlertCircle, Inbox, RefreshCw } from 'lucide-react'

export function LoadingState() {
  return (
    <div className="space-y-3">
      <div className="h-20 animate-pulse-soft rounded-2xl bg-white" />
      <div className="grid grid-cols-2 gap-2.5 md:grid-cols-4">
        {[0, 1, 2, 3].map((item) => (
          <div key={item} className="h-24 animate-pulse-soft rounded-2xl bg-white" />
        ))}
      </div>
      {[0, 1, 2].map((item) => (
        <div key={item} className="h-64 animate-pulse-soft rounded-2xl bg-white" />
      ))}
    </div>
  )
}

export function EmptyState({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-6 py-16 text-center shadow-sm">
      <Inbox className="mx-auto h-8 w-8 text-slate-300" />
      <p className="mt-3 text-[15px] font-semibold text-slate-800">{title}</p>
      <p className="mt-1 text-[13px] text-slate-500">{hint}</p>
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="rounded-2xl border border-rose-100 bg-white px-6 py-14 text-center shadow-sm">
      <AlertCircle className="mx-auto h-8 w-8 text-rose-500" />
      <p className="mt-3 text-[15px] font-semibold text-slate-800">加载失败</p>
      <p className="mt-1 text-[13px] text-slate-500">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-4 inline-flex items-center gap-1 rounded-lg bg-slate-900 px-3 py-1.5 text-[13px] text-white"
      >
        <RefreshCw className="h-3.5 w-3.5" />
        重试
      </button>
    </div>
  )
}
