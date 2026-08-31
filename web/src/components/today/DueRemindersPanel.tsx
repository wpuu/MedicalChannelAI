import { BellRing, Check, ChevronRight } from 'lucide-react'
import { isApiMode } from '@/services/apiConfig'
import type { DueReminder } from '@/services/reminderApi'
import { formatDateTime } from '@/utils/format'

interface DueRemindersPanelProps {
  reminders: DueReminder[]
  currentOpportunityIds: string[]
  busyId: string | null
  onOpenToday: (opportunityId: string) => void
  onOpenFollowed: (opportunityId: string) => void
  onAcknowledge: (reminderId: string) => void
}

export function DueRemindersPanel({
  reminders,
  currentOpportunityIds,
  busyId,
  onOpenToday,
  onOpenFollowed,
  onAcknowledge,
}: DueRemindersPanelProps) {
  if (reminders.length === 0) return null
  const currentIds = new Set(currentOpportunityIds)

  return (
    <section className="rounded-2xl border border-amber-200 bg-amber-50/70 p-4 shadow-sm">
      <div className="flex items-start gap-2">
        <BellRing className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
        <div className="min-w-0 flex-1">
          <div>
            <h3 className="text-[14px] font-semibold text-amber-950">
              到期跟进提醒 · {reminders.length}
            </h3>
            <p className="mt-0.5 text-[12px] leading-5 text-amber-800">
              {isApiMode
                ? '站内提醒 · 打开医疗商机助手时显示，当前尚未接入微信、短信或系统 Push。'
                : '本地提醒 · 仅在当前浏览器打开医疗商机助手时显示，不会发送系统通知。'}
            </p>
          </div>

          <div className="mt-3 space-y-2">
            {reminders.map((item) => {
              const buyer = item.facts.hospital_name ?? item.facts.buyer_name ?? '采购单位暂无公开信息'
              const project = item.facts.project_name ?? '项目名称暂无公开信息'
              const busy = busyId === item.reminder_id
              const isToday = currentIds.has(item.opportunity_id)
              return (
                <div
                  key={item.reminder_id}
                  className="rounded-xl border border-amber-200 bg-white px-3 py-3"
                >
                  <p className="text-[13px] font-medium text-slate-900">{buyer}</p>
                  <p className="mt-0.5 text-[13px] leading-5 text-slate-700">{project}</p>
                  <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-500">
                    <span>到期：{formatDateTime(item.remind_at) ?? item.remind_at}</span>
                    {item.note ? <span>备注：{item.note}</span> : null}
                    {!isToday ? <span>当前不在今日 Top5 · 已保留在我的跟进</span> : null}
                  </div>
                  <div className="mt-3 flex flex-wrap justify-end gap-2">
                    <button
                      type="button"
                      onClick={() =>
                        isToday
                          ? onOpenToday(item.opportunity_id)
                          : onOpenFollowed(item.opportunity_id)
                      }
                      className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-[12px] text-slate-700"
                    >
                      {isToday ? '查看今日详情' : '查看我的跟进'}
                      <ChevronRight className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => onAcknowledge(item.reminder_id)}
                      className="inline-flex items-center gap-1 rounded-lg bg-amber-700 px-2.5 py-1.5 text-[12px] text-white disabled:opacity-50"
                    >
                      <Check className="h-3.5 w-3.5" />
                      {busy ? '处理中' : '已处理'}
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </section>
  )
}
