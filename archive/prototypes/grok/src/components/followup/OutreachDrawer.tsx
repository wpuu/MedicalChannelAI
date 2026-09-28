import { useEffect, useState } from 'react'
import { Copy, Loader2 } from 'lucide-react'
import { Drawer } from '@/components/ui/Drawer'
import { todayActionsService } from '@/services'
import type { OutreachDraft } from '@/types'
import { useToast } from '@/context/ToastContext'

interface OutreachDrawerProps {
  open: boolean
  opportunityId: string | null
  onClose: () => void
}

export function OutreachDrawer({ open, opportunityId, onClose }: OutreachDrawerProps) {
  const { toast } = useToast()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState<OutreachDraft | null>(null)

  useEffect(() => {
    if (!open || !opportunityId) return
    let cancelled = false
    setLoading(true)
    setError(null)
    setDraft(null)
    todayActionsService
      .requestOutreachDraft(opportunityId)
      .then((res) => {
        if (!cancelled) setDraft(res)
      })
      .catch(() => {
        if (!cancelled) setError('话术生成失败，请稍后重试')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, opportunityId])

  const copyDraft = async () => {
    if (!draft) return
    try {
      await navigator.clipboard.writeText(draft.draft)
      toast('演示模式：话术已复制到剪贴板', 'success')
    } catch {
      toast('复制失败，请手动选择文本')
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title="生成沟通话术"
      subtitle="按需生成 · 不是官方事实"
      footer={
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-200 px-3 py-1.5 text-[13px] text-slate-600"
          >
            关闭
          </button>
          <button
            type="button"
            disabled={!draft}
            onClick={copyDraft}
            className="inline-flex items-center gap-1 rounded-lg bg-teal-700 px-3 py-1.5 text-[13px] text-white disabled:opacity-50"
          >
            <Copy className="h-3.5 w-3.5" />
            复制话术
          </button>
        </div>
      }
    >
      <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] leading-5 text-amber-900">
        演示模式 · 正式版将根据当前商机事实和客户资源按需生成
      </div>
      {loading ? (
        <div className="mt-8 flex flex-col items-center justify-center gap-2 text-slate-500">
          <Loader2 className="h-5 w-5 animate-spin" />
          <p className="text-[13px]">正在按当前事实与客户资源起草…</p>
        </div>
      ) : null}
      {error ? <p className="mt-6 text-[13px] text-rose-700">{error}</p> : null}
      {draft ? (
        <div className="mt-4">
          <p className="text-[12px] leading-5 text-slate-500">{draft.disclaimer}</p>
          <pre className="mt-3 whitespace-pre-wrap break-words rounded-xl border border-slate-200 bg-white p-3 font-sans text-[13px] leading-6 text-slate-800">
            {draft.draft}
          </pre>
        </div>
      ) : null}
    </Drawer>
  )
}
