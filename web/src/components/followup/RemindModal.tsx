import { useEffect, useMemo, useState } from 'react'
import { Modal } from '@/components/ui/Modal'
import { isApiMode } from '@/services/apiConfig'
import { isoDaysFromNow } from '@/utils/format'

interface RemindModalProps {
  open: boolean
  onClose: () => void
  onConfirm: (remindAt: string, nextAction: string) => void
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

export function RemindModal({ open, onClose, onConfirm }: RemindModalProps) {
  const presets = useMemo(
    () => [
      { label: '明天', value: isoDaysFromNow(1) },
      { label: '3 天后', value: isoDaysFromNow(3) },
      { label: '下周', value: isoDaysFromNow(7) },
    ],
    [],
  )
  const [selected, setSelected] = useState(presets[0].value)
  const [nextAction, setNextAction] = useState('')
  const remindAt = localDateAtNineToIso(selected)
  const normalizedNextAction = nextAction.trim()

  useEffect(() => {
    if (!open) return
    setSelected(presets[0].value)
    setNextAction('')
  }, [open, presets])

  return (
    <Modal
      open={open}
      title="安排下一步"
      onClose={onClose}
      footer={
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-200 px-3 py-1.5 text-[13px] text-slate-600"
          >
            取消
          </button>
          <button
            type="button"
            disabled={!remindAt || !normalizedNextAction}
            onClick={() => {
              if (remindAt && normalizedNextAction) onConfirm(remindAt, normalizedNextAction)
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
        onChange={(e) => setSelected(e.target.value)}
        className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-[13px] outline-none focus:border-teal-700"
      />

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
