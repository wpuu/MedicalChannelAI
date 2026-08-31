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

interface FollowupCardProps {
  card: TodayActionCard
  onChangeStatus: (status: FollowupStatus) => void
  onNotFit: () => void
  onRemind: () => void
}

export function FollowupCard({ card, onChangeStatus, onNotFit, onRemind }: FollowupCardProps) {
  const [status, setStatus] = useState<FollowupStatus>(card.followup_status)

  useEffect(() => {
    setStatus(card.followup_status)
  }, [card.followup_status])

  return (
    <SectionCard
      title="跟进记录"
      subtitle={
        isApiMode
          ? '销售跟进时间线 · 客户私有状态保存在服务器'
          : '销售跟进时间线 · 试用状态保存在当前浏览器'
      }
    >
      <div className="mb-4">
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
              if (status === 'MONITOR') {
                onRemind()
                return
              }
              onChangeStatus(status)
            }}
            className="shrink-0 rounded-lg bg-slate-900 px-3 py-2 text-[13px] text-white"
          >
            保存
          </button>
        </div>
      </div>

      {card.remind_at ? (
        <p className="mb-3 rounded-lg bg-amber-50 px-3 py-2 text-[12px] text-amber-800">
          {isApiMode ? '站内提醒' : '本地提醒'}：{formatDate(card.remind_at)}
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
                  <p className="mt-1 text-[12px] text-slate-600">{item.note}</p>
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
