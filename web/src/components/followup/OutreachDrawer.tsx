import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Copy, Loader2 } from 'lucide-react'
import { Drawer } from '@/components/ui/Drawer'
import { todayActionsService } from '@/services'
import { isAuthRequiredError } from '@/services/apiConfig'
import type { OutreachDraft } from '@/types'
import { useToast } from '@/context/ToastContext'

interface OutreachDrawerProps {
  open: boolean
  opportunityId: string | null
  onClose: () => void
}

const GROUP_RECIPIENT = '__GROUP__'

function outreachErrorMessage(error: unknown): string {
  if (!(error instanceof Error)) return '沟通草稿生成失败，请稍后重试'
  if (error.message === 'OUTREACH_GROUNDING_INSUFFICIENT' || error.message === 'HTTP_409') {
    return '当前商机的公开依据不足，暂不能生成沟通草稿。'
  }
  if (error.message === 'VERIFIED_SNAPSHOT_NOT_FRESH') {
    return '公开商机快照已超过安全刷新窗口，请先核对官方依据，待数据刷新后再生成沟通草稿。'
  }
  if (error.message === 'OPPORTUNITY_WINDOW_CLOSED') {
    return '当前项目的公开行动窗口已经结束，不再生成新的对外沟通草稿。'
  }
  if (error.message === 'VERIFIED_OPPORTUNITY_NOT_FOUND') {
    return '当前商机已不在已核验可行动商机池中，请刷新页面后重试。'
  }
  if (error.message === 'PRIVATE_PROFILE_UNAVAILABLE') {
    return '账号私有资源暂时无法读取，请稍后重试。'
  }
  if (error.message === 'PRIVATE_DATABASE_NOT_CONFIGURED') {
    return '试用账号数据库尚未配置完成。'
  }
  if (error.message === 'HTTP_429') {
    return '当前请求较多，请稍后再次生成。'
  }
  if (error.message === 'HTTP_503') {
    return '生成服务暂时不可用，请稍后再试。'
  }
  if (error.message === 'HTTP_502') {
    return '生成结果未通过事实校验，请稍后重试。'
  }
  return '沟通草稿生成失败，请稍后重试'
}

function contactNames(value: string): string[] {
  return value
    .split(/[、，,；;／/]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function personGreeting(name: string): string {
  const cleaned = name.trim()
  if (!cleaned) return '您好：'
  if (/(老师|先生|女士)$/.test(cleaned)) return `${cleaned}，您好：`
  return `${cleaned}老师，您好：`
}

function normalizeGreetingLine(
  value: string,
  recipientSelection: string,
  availableRecipients: string[],
): string {
  if (recipientSelection === GROUP_RECIPIENT) return '各位老师好：'
  if (recipientSelection) return personGreeting(recipientSelection)
  if (availableRecipients.length >= 2) return '您好：'
  if (availableRecipients.length === 1) return personGreeting(availableRecipients[0])

  const text = value.trim()
  if (/^各位老师[，,]?(?:您好|好)[：:]?$/.test(text)) return '您好：'
  if (/^老师[，,]?您好[：:]?$/.test(text) || /^您好[：:]?$/.test(text)) return '您好：'

  const match = text.match(/^(.+?)老师[，,]?(?:您好|好)[：:]?$/)
  if (!match) return value
  const names = contactNames(match[1])
  if (names.length >= 2) return '您好：'
  if (names.length === 1) return personGreeting(names[0])
  return '您好：'
}

function formatChineseDateTimeText(value: string): string {
  return value.replace(
    /(20\d{2})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})/g,
    (_whole, year: string, month: string, day: string, hour: string, minute: string) =>
      `${year}年${Number(month)}月${Number(day)}日 ${hour}:${minute}`,
  )
}

function normalizePublicationAttribution(value: string): string {
  const match = value.trim().match(/^关注到.+?公开发布了「(.+?)」。$/)
  if (!match) return value
  return `关注到「${match[1]}」的公开信息。`
}

function normalizeFormalProcurementWording(value: string): string {
  const formalProcurement =
    value.includes('招标文件获取') ||
    value.includes('投标/响应截止') ||
    value.includes('的公开采购信息。')
  if (!formalProcurement) return value
  return value
    .replace(
      '想确认目前是否还有公开答疑、技术交流或资料对接窗口；如方便，我们可以按项目要求准备相关资料。',
      '想确认目前是否还有公开答疑或公告允许的资料对接窗口；如方便，我们可以按项目要求准备相关资料。',
    )
    .replace(
      '想确认目前是否还有公开答疑、技术交流或资料对接窗口。',
      '想确认目前是否还有公开答疑或公告允许的资料对接窗口。',
    )
}

function toSendableDraft(
  value: string,
  recipientSelection: string,
  availableRecipients: string[],
): string {
  const lines = value
    .split('\n')
    .filter((line) => {
      const text = line.trim()
      if (text === '【公开事实沟通草稿】') return false
      if (text.startsWith('说明：本草稿只使用公开采购事实')) return false
      return true
    })

  const firstContentIndex = lines.findIndex((line) => line.trim())
  if (firstContentIndex >= 0) {
    lines[firstContentIndex] = normalizeGreetingLine(
      lines[firstContentIndex],
      recipientSelection,
      availableRecipients,
    )
  }
  for (let index = firstContentIndex + 1; index < lines.length; index += 1) {
    lines[index] = normalizePublicationAttribution(lines[index])
  }

  const formatted = formatChineseDateTimeText(lines.join('\n'))
    .replace(/\n{3,}/g, '\n\n')
    .trim()
  return normalizeFormalProcurementWording(formatted)
}

export function OutreachDrawer({ open, opportunityId, onClose }: OutreachDrawerProps) {
  const navigate = useNavigate()
  const { toast } = useToast()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState<OutreachDraft | null>(null)
  const [availableRecipients, setAvailableRecipients] = useState<string[]>([])
  const [recipientSelection, setRecipientSelection] = useState('')

  useEffect(() => {
    if (!open || !opportunityId) return
    let cancelled = false
    setLoading(true)
    setError(null)
    setDraft(null)
    setAvailableRecipients([])
    setRecipientSelection('')

    todayActionsService
      .getOpportunity(opportunityId)
      .then((card) => {
        if (cancelled) return
        const names = contactNames(card?.facts.official_contact?.name ?? '')
        setAvailableRecipients(names)
        if (names.length === 1) setRecipientSelection(names[0])
      })
      .catch(() => {
        // Recipient lookup is only a convenience layer. A neutral greeting remains safe.
      })

    void todayActionsService
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

  const sendableDraft = useMemo(
    () =>
      draft
        ? toSendableDraft(draft.draft, recipientSelection, availableRecipients)
        : '',
    [availableRecipients, draft, recipientSelection],
  )

  const copyDraft = async () => {
    if (!sendableDraft) return
    try {
      await navigator.clipboard.writeText(sendableDraft)
      toast('沟通内容已复制', 'success')
    } catch {
      toast('复制失败，请手动选择文本')
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title="沟通草稿"
      subtitle="可直接复制，发送前按实际情况修改"
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
            disabled={!sendableDraft}
            onClick={copyDraft}
            className="inline-flex items-center gap-1 rounded-lg bg-teal-700 px-3 py-1.5 text-[13px] text-white disabled:opacity-50"
          >
            <Copy className="h-3.5 w-3.5" />
            复制内容
          </button>
        </div>
      }
    >
      {loading ? (
        <div className="mt-8 flex flex-col items-center justify-center gap-2 text-slate-500">
          <Loader2 className="h-5 w-5 animate-spin" />
          <p className="text-[13px]">正在生成沟通内容…</p>
        </div>
      ) : null}
      {error ? <p className="mt-6 text-[13px] text-rose-700">{error}</p> : null}
      {draft ? (
        <div className="mt-2">
          {availableRecipients.length > 1 ? (
            <div className="mb-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
              <p className="text-[12px] font-medium text-slate-700">称呼对象</p>
              <p className="mt-0.5 text-[11px] leading-5 text-slate-500">
                公告列出多位联系人，不代表本次需要群发；默认不指定收件人。
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <button
                  type="button"
                  onClick={() => setRecipientSelection('')}
                  className={`rounded-full border px-2.5 py-1 text-[11px] ${
                    recipientSelection === ''
                      ? 'border-teal-600 bg-teal-50 text-teal-800'
                      : 'border-slate-200 bg-white text-slate-600'
                  }`}
                >
                  不指定
                </button>
                {availableRecipients.map((name) => (
                  <button
                    key={name}
                    type="button"
                    onClick={() => setRecipientSelection(name)}
                    className={`rounded-full border px-2.5 py-1 text-[11px] ${
                      recipientSelection === name
                        ? 'border-teal-600 bg-teal-50 text-teal-800'
                        : 'border-slate-200 bg-white text-slate-600'
                    }`}
                  >
                    {name}
                  </button>
                ))}
                <button
                  type="button"
                  onClick={() => setRecipientSelection(GROUP_RECIPIENT)}
                  className={`rounded-full border px-2.5 py-1 text-[11px] ${
                    recipientSelection === GROUP_RECIPIENT
                      ? 'border-teal-600 bg-teal-50 text-teal-800'
                      : 'border-slate-200 bg-white text-slate-600'
                  }`}
                >
                  各位老师
                </button>
              </div>
            </div>
          ) : null}
          <p className="mb-2 text-[12px] font-medium text-slate-500">可复制内容</p>
          <pre className="whitespace-pre-wrap break-words rounded-xl border border-slate-200 bg-white p-3 font-sans text-[13px] leading-6 text-slate-800">
            {sendableDraft}
          </pre>
          <p className="mt-2 text-[11px] leading-5 text-slate-400">
            提示：{draft.disclaimer}
          </p>
        </div>
      ) : null}
    </Drawer>
  )
}
