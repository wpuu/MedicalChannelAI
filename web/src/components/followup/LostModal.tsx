import { useState } from 'react'
import { Modal } from '@/components/ui/Modal'
import { LOST_REASONS } from '@/utils/labels'
import { isApiMode } from '@/services/apiConfig'
import type { LostReason } from '@/types'
import { useOutcomeSave } from './useOutcomeSave'

interface LostModalProps {
  open: boolean
  onClose: () => void
  onConfirm: (reason: LostReason) => boolean | Promise<boolean>
}

export function LostModal({ open, onClose, onConfirm }: LostModalProps) {
  const [reason, setReason] = useState<LostReason>('价格/报价竞争失败')
  const { saving, failed, close, confirm } = useOutcomeSave(onConfirm, onClose)

  return (
    <Modal
      open={open}
      title="标记为未成交"
      onClose={close}
      footer={
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={close}
            disabled={saving}
            className="rounded-lg border border-slate-200 px-3 py-1.5 text-[13px] text-slate-600"
          >
            取消
          </button>
          <button
            type="button"
            onClick={() => void confirm(reason)}
            disabled={saving}
            className="rounded-lg bg-slate-900 px-3 py-1.5 text-[13px] text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            确认未成交
          </button>
        </div>
      }
    >
      <p className="mb-3 text-[13px] leading-6 text-slate-500">
        {isApiMode
          ? '请选择你判断的未成交原因。该原因属于当前账号私有复盘数据，会保存到服务器；它不是医院或采购方公开确认的事实。'
          : '请选择你判断的未成交原因。演示模式下只保存在当前浏览器；它不是医院或采购方公开确认的事实。'}
      </p>
      {failed ? <p role="alert" className="mb-3 text-[12px] text-rose-700">保存失败，原因已保留，请重试。</p> : null}
      <div className="space-y-1.5">
        {LOST_REASONS.map((item) => (
          <label
            key={item}
            className="flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-slate-50"
          >
            <input
              type="radio"
              name="lost-reason"
              checked={reason === item}
              disabled={saving}
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
