import { BellRing, Check, ChevronRight } from 'lucide-react'
import type { DueReminder } from '@/services/reminderApi'
import { formatDateTime } from '@/utils/format'

interface DueRemindersPanelProps {
  reminders: DueReminder[]
  busyId: string | null
  onOpen: (opportunityId: string) => void
  onAcknowledge: (reminderId: string) => void
}

export function DueRemindersPanel({
  reminders,
  busyId,
  onOpen,
  onAcknowledge,
}: DueRemindersPanelProps) {
  if (reminders.length === 0) return null

  return (
    <section className="rounded-2xl border border-amber-200 bg-amber-50/70 p-4 shadow-sm">
      <div className="flex items-start gap-2">
        <BellRing className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="text-[14px] font-semibold text-amber-950">
                到期跟进提醒 · {reminders.length}
              </h3>
              <p className="mt-0.5 text-[12px] leading-5 text-amber-800">
                站内提醒 · 打开医疗商机助手时显示，当前尚未接入微信、短信或系统 Push。
              </p>
            </div>
          </div>

          <div className="mt-3 space-y-2">
            {reminders.map((item) => {
              const buyer = item.facts.hospital_name ?? item.facts.buyer_name ?? '采购单位暂无公开信息'
              const project = item.facts.project_name ?? '项目名称暂无公开信息'
              const busy = busyId === item.reminder_id
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
                  </div>
                  <div className="mt-3 flex flex-wrap justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => onOpen(item.opportunity_id)}
                      className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-[12px] text-slate-700"
                    >
                      查看商机
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
