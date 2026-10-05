import { useEffect, useMemo, useState } from 'react'
import { Modal } from '@/components/ui/Modal'
import { isApiMode } from '@/services/apiConfig'
import { formatDateOnly, isoDaysFromNow } from '@/utils/format'

interface RemindModalProps {
  open: boolean
  onClose: () => void
  onConfirm: (remindAt: string, nextAction: string) => void | Promise<void>
  maxDate?: string | null
  deadlineHint?: string | null
}

const NEXT_ACTION_PRESETS = [
  '再次联系采购/设备科',
  '确认产品参数与匹配情况',
  '确认厂家/授权/供货能力',
  '查看项目最新进展',
] as const

function localDateAtNineToIso(localDate: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(localDate)) return null
  const value = new Date(`${localDate}T09:00:00`)
  if (Number.isNaN(value.getTime())) return null
  return value.toISOString()
}

function isOnOrBefore(value: string, maxDate: string | null | undefined): boolean {
  return !maxDate || value <= maxDate
}

export function RemindModal({
  open,
  onClose,
  onConfirm,
  maxDate = null,
  deadlineHint = null,
}: RemindModalProps) {
  const presets = useMemo(
    () => [
      { label: '明天', value: isoDaysFromNow(1) },
      { label: '3 天后', value: isoDaysFromNow(3) },
      { label: '下周', value: isoDaysFromNow(7) },
    ].filter((item) => isOnOrBefore(item.value, maxDate)),
    [maxDate],
  )
  const fallbackSelected = presets[0]?.value ?? maxDate ?? isoDaysFromNow(1)
  const [selected, setSelected] = useState(fallbackSelected)
  const [nextAction, setNextAction] = useState('')
  const [saving, setSaving] = useState(false)
  const selectedWithinDeadline = isOnOrBefore(selected, maxDate)
  const remindAt = selectedWithinDeadline ? localDateAtNineToIso(selected) : null
  const normalizedNextAction = nextAction.trim()

  useEffect(() => {
    if (!open) return
    setSelected(presets[0]?.value ?? maxDate ?? isoDaysFromNow(1))
    setNextAction('')
  }, [open, presets, maxDate])

  return (
    <Modal
      open={open}
      title="安排下一步"
      onClose={saving ? () => {} : onClose}
      footer={
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="rounded-lg border border-slate-200 px-3 py-1.5 text-[13px] text-slate-600"
          >
            取消
          </button>
          <button
            type="button"
            disabled={saving || !remindAt || !normalizedNextAction}
            onClick={async () => {
              if (saving || !remindAt || !normalizedNextAction) return
              setSaving(true)
              try {
                await onConfirm(remindAt, normalizedNextAction)
              } finally {
                setSaving(false)
              }
            }}
            className="rounded-lg bg-teal-700 px-3 py-1.5 text-[13px] text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            保存下一步
          </button>
        </div>
      }
    >
      <p className="mb-3 text-[13px] leading-6 text-slate-500">
        {isApiMode
          ? '下一步和提醒时间会保存到当前账号私有跟进数据；不会改变当前销售阶段。到期后在站内提醒中直接告诉你要做什么，当前尚未接入微信、短信或系统 Push。'
          : '演示模式：下一步和提醒只保存在当前浏览器，不会发送系统通知，也不会改变当前销售阶段。'}
      </p>
      {maxDate ? (
        <div className="mb-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] leading-5 text-rose-800">
          本次提醒最晚只能选 {formatDateOnly(maxDate) ?? maxDate}，避免把下一步安排到已核验正式窗口之后。
          {deadlineHint ? ` 依据：${deadlineHint}。` : ''}
          此限制只使用已核验官方截止时间，不会自行推算新的官方截止日期。
        </div>
      ) : null}
      <div className="flex flex-wrap gap-2">
        {presets.map((item) => (
          <button
            key={item.label}
            type="button"
            onClick={() => setSelected(item.value)}
            className={
              selected === item.value
                ? 'rounded-lg bg-teal-700 px-3 py-1.5 text-[13px] text-white'
                : 'rounded-lg border border-slate-200 px-3 py-1.5 text-[13px] text-slate-700'
            }
          >
            {item.label}
          </button>
        ))}
      </div>
      <label className="mt-4 block text-[12px] text-slate-500">自定义日期</label>
      <input
        type="date"
        value={selected}
        max={maxDate ?? undefined}
        onChange={(e) => setSelected(e.target.value)}
        className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-[13px] outline-none focus:border-teal-700"
      />
      {!selectedWithinDeadline ? (
        <p className="mt-1 text-[11px] leading-5 text-rose-700">所选日期超过本次已核验正式窗口，请提前安排。</p>
      ) : null}

      <div className="mt-4">
        <p className="text-[12px] font-medium text-slate-600">下一步行动</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {NEXT_ACTION_PRESETS.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setNextAction(item)}
              className={
                nextAction === item
                  ? 'rounded-lg bg-slate-900 px-2.5 py-1.5 text-[11px] text-white'
                  : 'rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-[11px] text-slate-600 hover:bg-slate-100'
              }
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      <label htmlFor="reminder-next-action" className="mt-3 block text-[12px] text-slate-500">
        具体说明（必填，可直接修改快捷选项）
      </label>
      <textarea
        id="reminder-next-action"
        value={nextAction}
        maxLength={500}
        rows={3}
        placeholder="例如：再联系设备科，确认参数要求和厂家授权情况。"
        onChange={(event) => setNextAction(event.target.value)}
        className="mt-1 w-full resize-y rounded-lg border border-slate-200 px-3 py-2 text-[13px] leading-5 text-slate-700 outline-none focus:border-teal-700"
      />
      <p className="mt-1 text-[11px] leading-5 text-slate-400">
        每个提醒都必须对应一个明确动作，避免只留下日期却不知道到时要做什么。
      </p>
    </Modal>
  )
}
