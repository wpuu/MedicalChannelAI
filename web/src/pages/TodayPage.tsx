import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Clock, Info } from 'lucide-react'
import { ActionCard } from '@/components/today/ActionCard'
import { DueRemindersPanel } from '@/components/today/DueRemindersPanel'
import { MetricCards } from '@/components/today/MetricCards'
import { EmptyState, ErrorState, LoadingState } from '@/components/shared/PageStates'
import { NotFitModal } from '@/components/followup/NotFitModal'
import { RemindModal } from '@/components/followup/RemindModal'
import { OutreachDrawer } from '@/components/followup/OutreachDrawer'
import { useToast } from '@/context/ToastContext'
import { todayActionsService } from '@/services'
import { isApiMode, isAuthRequiredError } from '@/services/apiConfig'
import {
  acknowledgeDueReminder,
  getDueReminders,
  type DueReminder,
} from '@/services/reminderApi'
import type { FollowupStatus, NotFitReason, TodayActionsResponse } from '@/types'
import { formatDateTime } from '@/utils/format'

export function TodayPage() {
  const navigate = useNavigate()
  const { toast } = useToast()
  const [data, setData] = useState<TodayActionsResponse | null>(null)
  const [reminders, setReminders] = useState<DueReminder[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [reminderBusyId, setReminderBusyId] = useState<string | null>(null)
  const [notFitId, setNotFitId] = useState<string | null>(null)
  const [remindId, setRemindId] = useState<string | null>(null)
  const [outreachId, setOutreachId] = useState<string | null>(null)

  const load = useCallback(async (silent = false) => {
    if (!silent) {
      setLoading(true)
      setError(null)
    }
    try {
      const res = await todayActionsService.getTodayActions()
      setData(res)
      if (isApiMode) {
        try {
          setReminders(await getDueReminders())
        } catch (cause) {
          if (isAuthRequiredError(cause)) {
            navigate('/login', { replace: true })
            return
          }
          // Reminder inbox is auxiliary; a temporary inbox failure must not hide Today Actions.
        }
      } else {
        setReminders([])
      }
    } catch (cause) {
      if (isAuthRequiredError(cause)) {
        navigate('/login', { replace: true })
        return
      }
      setError('今日行动加载失败，请稍后重试。')
    } finally {
      setLoading(false)
    }
  }, [navigate])

  useEffect(() => {
    void load()
  }, [load])

  const updateStatus = async (
    id: string,
    status: FollowupStatus,
    extra?: { reason?: string; remind_at?: string; note?: string },
  ) => {
    setBusyId(id)
    try {
      await todayActionsService.updateFollowup(id, { status, ...extra })
      await load(true)
      toast(
        isApiMode ? '跟进状态已同步服务器' : '演示模式：跟进状态已在本地更新',
        'success',
      )
    } catch (cause) {
      if (isAuthRequiredError(cause)) {
        navigate('/login', { replace: true })
        return
      }
      toast('跟进状态更新失败，请重试')
    } finally {
      setBusyId(null)
    }
  }

  const acknowledgeReminder = async (reminderId: string) => {
    setReminderBusyId(reminderId)
    try {
      await acknowledgeDueReminder(reminderId)
      setReminders((items) => items.filter((item) => item.reminder_id !== reminderId))
      toast('站内提醒已标记处理', 'success')
    } catch (cause) {
      if (isAuthRequiredError(cause)) {
        navigate('/login', { replace: true })
        return
      }
      toast('提醒处理失败，请重试')
    } finally {
      setReminderBusyId(null)
    }
  }

  if (loading) return <LoadingState />
  if (error) return <ErrorState message={error} onRetry={() => void load()} />
  if (!data) return <EmptyState title="暂无今日行动" hint="当前没有可展示的重点商机。" />

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">今天最值得做什么</h2>
            <p className="mt-1 text-[13px] leading-6 text-slate-500">
              从公开采购信息中筛出最多 5 个今日行动，并说明为什么值得跟。
            </p>
          </div>
          <div className="flex items-center gap-1.5 text-[12px] text-slate-500">
            <Clock className="h-3.5 w-3.5" />
            最近刷新 {formatDateTime(data.refreshed_at)}
          </div>
        </div>
        <div className="mt-3 flex items-start gap-2 rounded-xl border border-amber-100 bg-amber-50 px-3 py-2.5">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
          <p className="text-[13px] leading-5 text-amber-900">{data.coverage_warning}</p>
        </div>
        <p className="mt-2 text-[12px] text-slate-400">
          经营优先级用于安排销售资源，不代表中标概率。
        </p>
      </section>

      <DueRemindersPanel
        reminders={reminders}
        currentOpportunityIds={data.cards.map((card) => card.opportunity_id)}
        busyId={reminderBusyId}
        onOpen={(opportunityId) => navigate(`/opportunity/${opportunityId}`)}
        onAcknowledge={(reminderId) => void acknowledgeReminder(reminderId)}
      />

      <MetricCards data={data} />

      {data.cards.length === 0 ? (
        <EmptyState title="今日暂无重点行动" hint="匹配商机尚未达到需要今天采取行动的条件。" />
      ) : (
        <div className="space-y-3">
          {data.cards.map((card) => (
            <ActionCard
              key={card.opportunity_id}
              card={card}
              busy={busyId === card.opportunity_id}
              onDetail={() => navigate(`/opportunity/${card.opportunity_id}`)}
              onContacted={() => void updateStatus(card.opportunity_id, 'CONTACTED')}
              onFollow={() => void updateStatus(card.opportunity_id, 'REVIEWING')}
              onNotFit={() => setNotFitId(card.opportunity_id)}
              onRemind={() => setRemindId(card.opportunity_id)}
              onOutreach={() => setOutreachId(card.opportunity_id)}
            />
          ))}
        </div>
      )}

      <NotFitModal
        open={Boolean(notFitId)}
        onClose={() => setNotFitId(null)}
        onConfirm={(reason: NotFitReason) => {
          if (!notFitId) return
          const id = notFitId
          setNotFitId(null)
          void updateStatus(id, 'NOT_FIT', { reason })
        }}
      />
      <RemindModal
        open={Boolean(remindId)}
        onClose={() => setRemindId(null)}
        onConfirm={(remindAt) => {
          if (!remindId) return
          const id = remindId
          setRemindId(null)
          void updateStatus(id, 'MONITOR', {
            remind_at: remindAt,
            note: '稍后提醒',
          })
        }}
      />
      <OutreachDrawer
        open={Boolean(outreachId)}
        opportunityId={outreachId}
        onClose={() => setOutreachId(null)}
      />
    </div>
  )
}
