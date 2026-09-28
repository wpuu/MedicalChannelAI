import { Bell, Eye, MessageSquareText, Phone, RefreshCw, XCircle } from 'lucide-react'
import { cn } from '@/utils/cn'

interface ActionButtonsProps {
  onDetail: () => void
  onContacted: () => void
  onFollow: () => void
  onNotFit: () => void
  onRemind: () => void
  onOutreach: () => void
  busy?: boolean
}

export function ActionButtons({
  onDetail,
  onContacted,
  onFollow,
  onNotFit,
  onRemind,
  onOutreach,
  busy,
}: ActionButtonsProps) {
  const btn =
    'inline-flex min-h-9 items-center justify-center gap-1 rounded-lg border px-2.5 py-1.5 text-[12px] font-medium transition disabled:opacity-50'
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
      <button
        type="button"
        onClick={onDetail}
        className={cn(btn, 'col-span-2 border-teal-700 bg-teal-700 text-white sm:col-span-1')}
      >
        <Eye className="h-3.5 w-3.5" />
        查看详情
      </button>
      <button
        type="button"
        disabled={busy}
        onClick={onContacted}
        className={cn(btn, 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50')}
      >
        <Phone className="h-3.5 w-3.5" />
        已联系
      </button>
      <button
        type="button"
        disabled={busy}
        onClick={onFollow}
        className={cn(btn, 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50')}
      >
        <RefreshCw className="h-3.5 w-3.5" />
        继续跟进
      </button>
      <button
        type="button"
        disabled={busy}
        onClick={onNotFit}
        className={cn(btn, 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50')}
      >
        <XCircle className="h-3.5 w-3.5" />
        不适合
      </button>
      <button
        type="button"
        disabled={busy}
        onClick={onRemind}
        className={cn(btn, 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50')}
      >
        <Bell className="h-3.5 w-3.5" />
        稍后提醒
      </button>
      <button
        type="button"
        disabled={busy}
        onClick={onOutreach}
        className={cn(
          btn,
          'col-span-2 border-indigo-200 bg-indigo-50 text-indigo-800 hover:bg-indigo-100 sm:col-span-1',
        )}
      >
        <MessageSquareText className="h-3.5 w-3.5" />
        生成沟通话术
      </button>
    </div>
  )
}
