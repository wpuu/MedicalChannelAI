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
import {
  AiDecisionError,
  hydrateCachedAiDecisions,
  requestAiDecision,
} from '@/services/aiDecisionApi'
import { isApiMode, isAuthRequiredError } from '@/services/apiConfig'
import {
  acknowledgeDueReminder,
  getDueReminders,
  type DueReminder,
} from '@/services/reminderApi'
import type {
  FollowupStatus,
  NotFitReason,
  TodayActionCard,
  TodayActionsResponse,
} from '@/types'
import { formatDateTime } from '@/utils/format'

const DONE_FOR_TODAY = new Set<FollowupStatus>([
  'CONTACTED',
  'NOT_FIT',
  'BID_SUBMITTED',
  'WON',
  'LOST',
  'ARCHIVED',
])
const MAX_TODAY_CARDS = 5

function shouldHideFromVerifiedTrialToday(card: TodayActionCard): boolean {
  if (DONE_FOR_TODAY.has(card.followup_status)) return true
  if (card.followup_status !== 'MONITOR' || !card.remind_at) return false
  const remindAt = new Date(card.remind_at).getTime()
  return !Number.isNaN(remindAt) && remindAt > Date.now()
}

export function TodayPage() {
  const navigate = useNavigate()
  const { toast } = useToast()
  const [data, setData] = useState<TodayActionsResponse | null>(null)
  const [reminders, setReminders] = useState<DueReminder[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [aiBusyId, setAiBusyId] = useState<string | null>(null)
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
      if (!isApiMode && isVerifiedPublicDemo) {
        const pool = res.opportunity_pool ?? res.cards
        const hydratedPool = await hydrateCachedAiDecisions(pool)
        const cards = hydratedPool
          .filter((card) => !shouldHideFromVerifiedTrialToday(card))
          .slice(0, MAX_TODAY_CARDS)
        setData({
          ...res,
          matched_count: hydratedPool.length,
          card_count: cards.length,
          opportunity_pool_count: hydratedPool.length,
          cards,
          opportunity_pool: hydratedPool,
        })
      } else {
        setData(res)
      }

      try {
        setReminders(await getDueReminders())
      } catch (cause) {
        if (isAuthRequiredError(cause)) {
          navigate('/login', { replace: true })
          return
        }
        // Reminder inbox is auxiliary; a temporary failure must not hide Today Actions.
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
      if (isApiMode) {
        toast('跟进状态已同步服务器', 'success')
      } else if (status === 'CONTACTED') {
        toast('已联系，商机已移入“我的跟进”', 'success')
      } else if (status === 'NOT_FIT') {
        toast('已标记不适合，记录已保留在“我的跟进”', 'success')
      } else if (status === 'MONITOR' && extra?.remind_at) {
        toast('提醒已设置，提醒前暂不占用今日重点', 'success')
      } else {
        toast('试用模式：跟进状态已在本地更新', 'success')
      }
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

  const analyzeOpportunity = async (id: string) => {
    const card = data?.cards.find((item) => item.opportunity_id === id)
    if (!card || !isVerifiedPublicDemo || isApiMode) return

    setAiBusyId(id)
    try {
      const decision = await requestAiDecision(card)
      setData((current) => {
        if (!current) return current
        const updateCard = (item: TodayActionCard) =>
          item.opportunity_id === id
            ? {
                ...item,
                model_decision_status: 'READY' as const,
                model_block_reason: null,
                decision,
              }
            : item
        return {
          ...current,
          cards: current.cards.map(updateCard),
          opportunity_pool: current.opportunity_pool?.map(updateCard),
        }
      })
      toast('AI已基于公开事实给出行动建议', 'success')
    } catch (cause) {
      if (cause instanceof AiDecisionError) {
        if (cause.code === 'AI_NOT_CONFIGURED') {
          toast('AI服务运行配置尚未完成')
        } else if (cause.code === 'AI_RATE_LIMITED') {
          toast('AI服务当前限流，请稍后再试')
        } else if (cause.code === 'AI_PROVIDER_AUTH_UNAVAILABLE') {
          toast('AI服务当前不可用，请稍后再试')
        } else if (cause.code === 'AI_TIMEOUT') {
          toast('AI分析超时，请稍后重试')
        } else if (cause.code === 'OPPORTUNITY_WINDOW_CLOSED') {
          toast('该项目公开窗口已经结束，当前不再生成行动建议')
        } else if (cause.code === 'VERIFIED_OPPORTUNITY_NOT_FOUND') {
          toast('该商机暂不在服务端已核验快照中')
        } else {
          toast('AI分析暂时不可用，请稍后重试')
        }
      } else {
        toast('AI分析暂时不可用，请稍后重试')
      }
    } finally {
      setAiBusyId(null)
    }
  }

  const acknowledgeReminder = async (reminderId: string) => {
    setReminderBusyId(reminderId)
    try {
      await acknowledgeDueReminder(reminderId)
      await load(true)
      toast(isApiMode ? '站内提醒已标记处理' : '本地提醒已标记处理', 'success')
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

  const visibleCards =
    !isApiMode && isVerifiedPublicDemo
      ? data.cards.filter((card) => !shouldHideFromVerifiedTrialToday(card))
      : data.cards
  const visibleData = { ...data, card_count: visibleCards.length, cards: visibleCards }
  const poolCount = data.opportunity_pool_count ?? data.opportunity_pool?.length ?? data.matched_count

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">今天值得跟的医疗商机</h2>
            <p className="mt-1 text-[13px] leading-6 text-slate-500">
              不需要先录资料。先从公开采购信息里看最多 5 个重点项目、官方依据和下一步动作。
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
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <p className="text-[12px] text-slate-400">
            经营优先级用于安排销售资源，不代表中标概率。
          </p>
          {!isApiMode && isVerifiedPublicDemo && poolCount > visibleCards.length ? (
            <button
              type="button"
              onClick={() => navigate('/opportunities')}
              className="rounded-lg border border-teal-200 bg-teal-50 px-2.5 py-1.5 text-[12px] font-medium text-teal-800 hover:bg-teal-100"
            >
              查看全部 {poolCount} 条商机
            </button>
          ) : null}
        </div>
      </section>

      {!isApiMode ? (
        <section className="rounded-2xl border border-teal-200 bg-teal-50/70 px-4 py-4 shadow-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-md bg-teal-700 px-2 py-0.5 text-[11px] font-semibold text-white">
              {isVerifiedPublicDemo ? '零配置体验 · 真实公开项目' : '零配置体验 · 演示数据'}
            </span>
            <span className="text-[12px] text-teal-900">
              先直接看每天能发现什么；医院关系和产品资料以后再录，也能先判断这个产品有没有价值。
            </span>
          </div>
          <p className="mt-2 text-[13px] leading-6 text-slate-700">
            当前按“天津医疗渠道商”通用场景展示。公开采购事实和官方依据与客户侧资源严格分开；未录入真实客户资源，不影响先体验商机发现、项目核验和行动建议流程。
          </p>
          <div className="mt-3 flex flex-wrap gap-2 text-[11px]">
            {['无需先录资料', '最多5个重点', '官方依据可核验', '按需AI分析', '后续可个性化'].map((label) => (
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
              ? '当前试用读取证据流水线生成的天津公开事实快照。项目名称、采购单位、预算、公告日期、精确截止时间、公开联系人和官方依据来自已核验公开信息；未录入真实客户资源时，医院关系和产品能力明确为空，不参与排序。AI分析按单条商机手动触发，只接收服务端已核验公开事实。已联系、不适合和设置未来提醒的项目会移入“我的跟进”，系统会从商机池自动补足新的今日重点。自动刷新链已准备，当前试用仍按已验证快照展示，不冒充实时全量数据。'
              : '下方项目、医院、联系人和金额均为虚构演示数据。排序来自通用演示场景，不代表真实客户当前资源。'}
          </p>
        </section>
      ) : null}

      <DueRemindersPanel
        reminders={reminders}
        currentOpportunityIds={visibleCards.map((card) => card.opportunity_id)}
        busyId={reminderBusyId}
        onOpenToday={(opportunityId) => navigate(`/opportunity/${opportunityId}`)}
        onOpenFollowed={(opportunityId) => navigate(`/followed?focus=${encodeURIComponent(opportunityId)}`)}
        onAcknowledge={(reminderId) => void acknowledgeReminder(reminderId)}
      />

      <MetricCards data={visibleData} />

      {visibleCards.length === 0 ? (
        <EmptyState title="今日暂无重点行动" hint="公开项目尚未达到需要今天采取行动的条件，或当前重点已处理。" />
      ) : (
        <div className="space-y-3">
          {visibleCards.map((card) => (
            <ActionCard
              key={card.opportunity_id}
              card={card}
              busy={busyId === card.opportunity_id}
              aiBusy={aiBusyId === card.opportunity_id}
              onDetail={() => navigate(`/opportunity/${card.opportunity_id}`)}
              onContacted={() => void updateStatus(card.opportunity_id, 'CONTACTED')}
              onFollow={() => void updateStatus(card.opportunity_id, 'REVIEWING')}
              onNotFit={() => setNotFitId(card.opportunity_id)}
              onRemind={() => setRemindId(card.opportunity_id)}
              onOutreach={() => setOutreachId(card.opportunity_id)}
              onAnalyze={
                isVerifiedPublicDemo && !isApiMode
                  ? () => void analyzeOpportunity(card.opportunity_id)
                  : undefined
              }
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
