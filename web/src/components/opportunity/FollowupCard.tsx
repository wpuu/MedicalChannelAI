import { useEffect, useState } from 'react'
import type { FollowupStatus, TodayActionCard } from '@/types'
import { SectionCard } from '@/components/shared/SectionCard'
import { formatDate, formatDateTime } from '@/utils/format'
import { FOLLOWUP_STATUS_LABEL } from '@/utils/labels'
import { isApiMode } from '@/services/apiConfig'

const STATUS_OPTIONS: FollowupStatus[] = [
  'NEW',
  'REVIEWING',
  'CONTACTED',
  'RELATIONSHIP_VERIFIED',
  'PREPARING',
  'BID_SUBMITTED',
  'WON',
  'LOST',
  'NOT_FIT',
  'MONITOR',
  'ARCHIVED',
]
const REMINDER_TERMINAL_STATUSES = new Set<FollowupStatus>([
  'WON',
  'LOST',
  'NOT_FIT',
  'ARCHIVED',
])

interface FollowupCardProps {
  card: TodayActionCard
  onChangeStatus: (status: FollowupStatus) => void
  onAddNote?: (note: string) => Promise<boolean>
  onNotFit: () => void
  onRemind: () => void
  readOnly?: boolean
}

export function FollowupCard({
  card,
  onChangeStatus,
  onAddNote,
  onNotFit,
  onRemind,
  readOnly = false,
}: FollowupCardProps) {
  const [status, setStatus] = useState<FollowupStatus>(card.followup_status)
  const [note, setNote] = useState('')
  const [savingNote, setSavingNote] = useState(false)
  const reminderAllowed = !REMINDER_TERMINAL_STATUSES.has(card.followup_status)

  useEffect(() => {
    setStatus(card.followup_status)
  }, [card.followup_status])

  const saveNote = async () => {
    const value = note.trim()
    if (!value || !onAddNote || savingNote) return
    setSavingNote(true)
    try {
      const saved = await onAddNote(value)
      if (saved) setNote('')
    } finally {
      setSavingNote(false)
    }
  }

  return (
    <SectionCard
      title="跟进记录"
      subtitle={
        readOnly
          ? '历史跟进快照 · 仅查看已保存记录'
          : isApiMode
            ? '销售跟进时间线 · 客户私有状态保存在服务器'
            : '销售跟进时间线 · 试用状态保存在当前浏览器'
      }
    >
      {!readOnly ? (
        <div className="mb-4 space-y-3">
          <div>
            <label className="text-[12px] text-slate-500">更新跟进状态</label>
            <div className="mt-2 flex gap-2">
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value as FollowupStatus)}
                className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] outline-none focus:border-teal-700"
              >
                {STATUS_OPTIONS.map((item) => (
                  <option key={item} value={item}>
                    {FOLLOWUP_STATUS_LABEL[item]}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => {
                  if (status === 'NOT_FIT') {
                    onNotFit()
                    return
                  }
                  onChangeStatus(status)
                }}
                className="shrink-0 rounded-lg bg-slate-900 px-3 py-2 text-[13px] text-white"
              >
                保存状态
              </button>
            </div>
            <div className="mt-2 flex items-center justify-between gap-2">
              <p className="text-[11px] leading-5 text-slate-400">
                {reminderAllowed
                  ? '“持续观察”只是销售阶段；提醒时间独立保存，不会自动改写当前阶段。'
                  : '当前项目已结束，不再新增后续提醒。'}
              </p>
              {reminderAllowed ? (
                <button
                  type="button"
                  onClick={onRemind}
                  className="shrink-0 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-[11px] font-medium text-amber-800 hover:bg-amber-100"
                >
                  设置提醒
                </button>
              ) : null}
            </div>
          </div>

          {onAddNote ? (
            <div className="rounded-xl border border-slate-100 bg-slate-50 p-3">
              <label htmlFor={`followup-note-${card.opportunity_id}`} className="text-[12px] font-medium text-slate-600">
                记录本次跟进
              </label>
              <textarea
                id={`followup-note-${card.opportunity_id}`}
                value={note}
                maxLength={2000}
                rows={3}
                placeholder="例如：已电话联系设备科，对方建议周四再联系；下一步确认参数和厂家授权。"
                onChange={(event) => setNote(event.target.value)}
                className="mt-2 w-full resize-y rounded-lg border border-slate-200 bg-white px-3 py-2 text-[13px] leading-5 text-slate-700 outline-none focus:border-teal-600"
              />
              <div className="mt-2 flex items-center justify-between gap-3">
                <span className="text-[11px] text-slate-400">{note.length}/2000 · 备注属于当前账号私有数据</span>
                <button
                  type="button"
                  disabled={!note.trim() || savingNote}
                  onClick={() => void saveNote()}
                  className="shrink-0 rounded-lg border border-teal-200 bg-teal-50 px-3 py-1.5 text-[12px] font-medium text-teal-800 hover:bg-teal-100 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {savingNote ? '保存中…' : '保存备注'}
                </button>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      {card.remind_at ? (
        <p className="mb-3 rounded-lg bg-amber-50 px-3 py-2 text-[12px] text-amber-800">
          {readOnly ? '已保存提醒' : isApiMode ? '站内提醒' : '本地提醒'}：{formatDate(card.remind_at)}
        </p>
      ) : null}

      {card.followup_history.length === 0 ? (
        <p className="text-[13px] text-slate-400">暂无跟进记录</p>
      ) : (
        <ol className="space-y-3">
          {card.followup_history.map((item, index) => (
            <li key={item.id} className="flex gap-3">
              <div className="flex flex-col items-center">
                <span
                  className={`mt-1 h-2.5 w-2.5 rounded-full ${
                    index === 0 ? 'bg-teal-700' : 'bg-slate-300'
                  }`}
                />
                {index !== card.followup_history.length - 1 ? (
                  <span className="w-px flex-1 bg-slate-200" />
                ) : null}
              </div>
              <div className="min-w-0 pb-2">
                <p className="text-[13px] font-medium text-slate-800">
                  {FOLLOWUP_STATUS_LABEL[item.status]}
                </p>
                <p className="text-[12px] text-slate-500">
                  {item.actor} · {formatDateTime(item.at)}
                </p>
                {item.reason ? (
                  <p className="mt-1 text-[12px] text-slate-600">原因：{item.reason}</p>
                ) : null}
                {item.note ? (
                  <p className="mt-1 whitespace-pre-wrap text-[12px] leading-5 text-slate-600">{item.note}</p>
                ) : null}
                {item.remind_at ? (
                  <p className="mt-1 text-[12px] text-slate-600">
                    提醒日期：{formatDate(item.remind_at)}
                  </p>
                ) : null}
              </div>
            </li>
          ))}
        </ol>
      )}
    </SectionCard>
  )
}
