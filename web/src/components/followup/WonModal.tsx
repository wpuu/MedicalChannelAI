import { useState } from 'react'
import { Modal } from '@/components/ui/Modal'
import { WON_REASONS } from '@/utils/labels'
import { isApiMode } from '@/services/apiConfig'
import type { WonReason } from '@/types'

interface WonModalProps {
  open: boolean
  onClose: () => void
  onConfirm: (reason: WonReason) => void
}

export function WonModal({ open, onClose, onConfirm }: WonModalProps) {
  const [reason, setReason] = useState<WonReason>('产品或参数匹配')

  return (
    <Modal
      open={open}
      title="标记为已成交"
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
            className="rounded-lg bg-teal-700 px-3 py-1.5 text-[13px] text-white"
          >
            确认成交
          </button>
        </div>
      }
    >
      <p className="mb-3 text-[13px] leading-6 text-slate-500">
        {isApiMode
          ? '请选择你认为本次成交最值得复盘的因素。该内容属于当前账号私有商业判断，会保存到服务器；它不是医院或采购方公开确认的中标原因。'
          : '请选择你认为本次成交最值得复盘的因素。演示模式下只保存在当前浏览器；它不是医院或采购方公开确认的中标原因。'}
      </p>
      <div className="space-y-1.5">
        {WON_REASONS.map((item) => (
          <label
            key={item}
            className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-slate-50"
          >
            <input
              type="radio"
              name="won-reason"
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
