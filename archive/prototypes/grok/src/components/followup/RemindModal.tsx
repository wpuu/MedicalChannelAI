import { useMemo, useState } from 'react'
import { Modal } from '@/components/ui/Modal'
import { isoDaysFromNow } from '@/utils/format'

interface RemindModalProps {
  open: boolean
  onClose: () => void
  onConfirm: (remindAt: string) => void
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
            onClick={() => onConfirm(selected)}
            className="rounded-lg bg-teal-700 px-3 py-1.5 text-[13px] text-white"
          >
            设置提醒
          </button>
        </div>
      }
    >
      <p className="mb-3 text-[13px] leading-6 text-slate-500">
        提醒只会保存在本地浏览器，演示模式不会发送通知。
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
    </Modal>
  )
}
