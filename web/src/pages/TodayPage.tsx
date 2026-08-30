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
import { isVerifiedPublicDemo } from '@/config/demoDataset'
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

      {!isApiMode ? (
        <section className="rounded-2xl border border-teal-200 bg-teal-50/70 px-4 py-4 shadow-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-md bg-teal-700 px-2 py-0.5 text-[11px] font-semibold text-white">
              {isVerifiedPublicDemo ? '真实公开数据演示' : '虚构演示客户画像'}
            </span>
            <span className="text-[12px] text-teal-900">
              {isVerifiedPublicDemo
                ? '采购项目是真实公开事实；客户关系与产品资源仍是演示画像'
                : '用于说明“为什么这个客户今天应该先跟这5个项目”'}
            </span>
          </div>
          <p className="mt-2 text-[13px] leading-6 text-slate-700">
            天津医疗渠道商；已确认部分检验科、设备科医院关系；具备或可合作执行IVD、检验设备租赁、影像及医疗设备渠道项目。
          </p>
          <div className="mt-3 flex flex-wrap gap-2 text-[11px]">
            {['医院关系', 'IVD产品能力', '检验设备租赁', '可找厂家', '可联合渠道'].map((label) => (
              <span
                key={label}
                className="rounded-full border border-teal-200 bg-white px-2.5 py-1 font-medium text-teal-800"
              >
                {label}
              </span>
            ))}
          </div>
          <p className="mt-3 text-[12px] leading-5 text-slate-500">
            {isVerifiedPublicDemo
              ? '项目名称、采购单位、预算、公告日期、截止时间、公开联系人和官方依据来自2026-08-30冻结的政府采购公开信息快照；医院关系、产品能力、经营优先级及建议中的客户侧输入为演示数据。'
              : '下方项目、医院、联系人和金额均为虚构演示数据。排序来自“项目公开事实 × 这份客户资源”，不是全市场通用排名。'}
          </p>
        </section>
      ) : null}

      <DueRemindersPanel
        reminders={reminders}
        currentOpportunityIds={data.cards.map((card) => card.opportunity_id)}
        busyId={reminderBusyId}
        onOpenToday={(opportunityId) => navigate(`/opportunity/${opportunityId}`)}
        onOpenFollowed={(opportunityId) => navigate(`/followed?focus=${encodeURIComponent(opportunityId)}`)}
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