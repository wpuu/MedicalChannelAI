import { useEffect, useMemo, useState } from 'react'
import { Modal } from '@/components/ui/Modal'
import { isApiMode } from '@/services/apiConfig'
import { isoDaysFromNow } from '@/utils/format'

interface RemindModalProps {
  open: boolean
  onClose: () => void
  onConfirm: (remindAt: string, nextAction: string | null) => void
}

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

  useEffect(() => {
    if (!open) return
    setSelected(presets[0].value)
    setNextAction('')
  }, [open, presets])

  return (
    <Modal
      open={open}
      title="稍后提醒"
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
            disabled={!remindAt}
            onClick={() => remindAt && onConfirm(remindAt, nextAction.trim() || null)}
            className="rounded-lg bg-teal-700 px-3 py-1.5 text-[13px] text-white disabled:opacity-50"
          >
            设置提醒
          </button>
        </div>
      }
    >
      <p className="mb-3 text-[13px] leading-6 text-slate-500">
        {isApiMode
          ? '提醒时间会保存到服务器，默认按所选日期当地时间 09:00 到期；设置提醒不会改变当前销售阶段。当前 Pilot 先提供站内到期提醒，尚未接入微信、短信或系统 Push。'
          : '演示模式：提醒只保存在当前浏览器，不会发送通知，也不会改变当前销售阶段。'}
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
      <label htmlFor="reminder-next-action" className="mt-4 block text-[12px] font-medium text-slate-600">
        到时要做什么（可选）
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
        填写后会作为当前账号私有跟进备注保存，并在到期提醒里直接显示。
      </p>
    </Modal>
  )
}
