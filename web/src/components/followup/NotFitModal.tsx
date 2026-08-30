import { useState } from 'react'
import { Modal } from '@/components/ui/Modal'
import { NOT_FIT_REASONS } from '@/utils/labels'
import type { NotFitReason } from '@/types'

interface NotFitModalProps {
  open: boolean
  onClose: () => void
  onConfirm: (reason: NotFitReason) => void
}

export function NotFitModal({ open, onClose, onConfirm }: NotFitModalProps) {
  const [reason, setReason] = useState<NotFitReason>('没有对应产品')

  return (
    <Modal
      open={open}
      title="标记为不适合"
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
            onClick={() => onConfirm(reason)}
            className="rounded-lg bg-slate-900 px-3 py-1.5 text-[13px] text-white"
          >
            确认
          </button>
        </div>
      }
    >
      <p className="mb-3 text-[13px] leading-6 text-slate-500">
        请选择原因。该操作仅保存在本地演示状态，不会写入服务器。
      </p>
      <div className="space-y-1.5">
        {NOT_FIT_REASONS.map((item) => (
          <label
            key={item}
            className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-slate-50"
          >
            <input
              type="radio"
              name="not-fit-reason"
              checked={reason === item}
              onChange={() => setReason(item)}
              className="accent-teal-700"
            />
            <span className="text-[13px] text-slate-700">{item}</span>
          </label>
        ))}
      </div>
    </Modal>
  )
}
