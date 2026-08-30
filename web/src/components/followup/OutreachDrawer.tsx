import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Copy, Loader2 } from 'lucide-react'
import { Drawer } from '@/components/ui/Drawer'
import { todayActionsService } from '@/services'
import { isApiMode, isAuthRequiredError } from '@/services/apiConfig'
import type { OutreachDraft } from '@/types'
import { useToast } from '@/context/ToastContext'

interface OutreachDrawerProps {
  open: boolean
  opportunityId: string | null
  onClose: () => void
}

function outreachErrorMessage(error: unknown): string {
  if (!(error instanceof Error)) return '话术生成失败，请稍后重试'
  if (error.message === 'HTTP_409') {
    return '当前商机的已验证公开依据或客户资源不足，暂不能安全生成话术。'
  }
  if (error.message === 'HTTP_429') {
    return '当前 AI 请求较多，请稍后再次生成。'
  }
  if (error.message === 'HTTP_503') {
    return '当前服务器尚未配置话术模型服务。'
  }
  if (error.message === 'HTTP_502') {
    return '模型返回结果未通过事实约束校验，请稍后重试。'
  }
  return '话术生成失败，请稍后重试'
}

export function OutreachDrawer({ open, opportunityId, onClose }: OutreachDrawerProps) {
  const navigate = useNavigate()
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
      .catch((cause: unknown) => {
        if (cancelled) return
        if (isAuthRequiredError(cause)) {
          onClose()
          navigate('/login', { replace: true })
          return
        }
        setError(outreachErrorMessage(cause))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [navigate, onClose, open, opportunityId])

  const copyDraft = async () => {
    if (!draft) return
    try {
      await navigator.clipboard.writeText(draft.draft)
      toast(isApiMode ? '话术已复制到剪贴板' : '演示模式：话术已复制到剪贴板', 'success')
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
        {isApiMode
          ? '天津 Pilot · 仅根据已验证公开事实与当前客户确认资源按需生成；最终话术不是医院官方表述。'
          : '演示模式 · 正式版将根据当前商机事实和客户资源按需生成'}
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
