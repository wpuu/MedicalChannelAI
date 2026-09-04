import { useState } from 'react'
import { Modal } from '@/components/ui/Modal'
import { NOT_FIT_REASONS } from '@/utils/labels'
import { isApiMode } from '@/services/apiConfig'
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
        {isApiMode
          ? '请选择原因。原因属于当前账号私有跟进数据，会保存到服务器，不会写入公开商机事实。'
          : '请选择原因。演示模式下只保存在当前浏览器，不会写入公开商机事实。'}
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
