import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Archive, Info, MessageSquareText, ShieldCheck } from 'lucide-react'
import { CustomerContextCard } from '@/components/opportunity/CustomerContextCard'
import { DecisionCard } from '@/components/opportunity/DecisionCard'
import { EvidenceCard } from '@/components/opportunity/EvidenceCard'
import { FactsCard } from '@/components/opportunity/FactsCard'
import { FollowupCard } from '@/components/opportunity/FollowupCard'
import { OpportunityExecutionCard } from '@/components/opportunity/OpportunityExecutionCard'
import { PriorityCard } from '@/components/opportunity/PriorityCard'
import { PublicHistoryCard } from '@/components/opportunity/PublicHistoryCard'
import { EmptyState, ErrorState, LoadingState } from '@/components/shared/PageStates'
import { PriorityBadge } from '@/components/shared/PriorityBadge'
import { LostModal } from '@/components/followup/LostModal'
import { NotFitModal } from '@/components/followup/NotFitModal'
import { RemindModal } from '@/components/followup/RemindModal'
import { OutreachDrawer } from '@/components/followup/OutreachDrawer'
import { WonModal } from '@/components/followup/WonModal'
import { OfficialText } from '@/components/shared/EmptyValue'
import { isVerifiedPublicDemo } from '@/config/demoDataset'
import { useToast } from '@/context/ToastContext'
import { todayActionsService } from '@/services'
import {
  AiDecisionError,
  aiDecisionErrorMessage,
  hydrateCachedAiDecisions,
  requestAiDecision,
} from '@/services/aiDecisionApi'
import { isApiMode, isAuthRequiredError } from '@/services/apiConfig'
import { getHistoricalFollowedOpportunityCard } from '@/services/followedApi'
import { getStoredHistoricalOpportunityCard } from '@/services/localFollowupStore'
import {
  getPublicOpportunityHistory,
  type PublicOpportunityHistory,
} from '@/services/publicOpportunityHistoryApi'
import {
  getRuntimeStatus,
  runtimeAutomationUnavailableReason,
  runtimeSnapshotWarning,
  type RuntimeStatus,
} from '@/services/runtimeStatusApi'
import type { FollowupStatus, LostReason, NotFitReason, TodayActionCard, WonReason } from '@/types'

const AI_UNCONFIGURED_REASON = 'AI暂时不可用，可稍后重试；其他功能正常。'

export function OpportunityDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { toast } = useToast()
  const [card, setCard] = useState<TodayActionCard | null>(null)
  const [historical, setHistorical] = useState(false)
  const [publicHistory, setPublicHistory] = useState<PublicOpportunityHistory | null>(null)
  const [publicHistoryLoading, setPublicHistoryLoading] = useState(false)
  const [publicHistoryError, setPublicHistoryError] = useState(false)
  const [runtimeStatus, setRuntimeStatus] = useState<RuntimeStatus | null>(null)
  const [runtimeStatusChecked, setRuntimeStatusChecked] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [wonOpen, setWonOpen] = useState(false)
  const [notFitOpen, setNotFitOpen] = useState(false)
  const [lostOpen, setLostOpen] = useState(false)
  const [remindOpen, setRemindOpen] = useState(false)
  const [outreachOpen, setOutreachOpen] = useState(false)
  const [aiBusy, setAiBusy] = useState(false)

  const loadPublicHistory = useCallback((opportunityId: string) => {
    if (!isApiMode) {
      setPublicHistory(null)
      setPublicHistoryLoading(false)
      setPublicHistoryError(false)
      return
    }
    setPublicHistoryLoading(true)
    setPublicHistoryError(false)
    void getPublicOpportunityHistory(opportunityId)
      .then((history) => setPublicHistory(history))
      .catch((cause) => {
        if (isAuthRequiredError(cause)) {
          navigate('/login', { replace: true })
          return
        }
        setPublicHistoryError(true)
      })
      .finally(() => setPublicHistoryLoading(false))
  }, [navigate])

  const load = useCallback(async (silent = false) => {
    if (!id) {
      setNotFound(true)
      setLoading(false)
      return
    }
    if (!silent) {
      setLoading(true)
      setError(null)
      setPublicHistory(null)
      setPublicHistoryLoading(false)
      setPublicHistoryError(false)
    }
    setNotFound(false)
    setHistorical(false)
    try {
      const res = await todayActionsService.getOpportunity(id)
      if (!res) {
        const stored = isApiMode
          ? await getHistoricalFollowedOpportunityCard(id)
          : isVerifiedPublicDemo
            ? getStoredHistoricalOpportunityCard(id)
            : null
        if (stored) {
          setHistorical(true)
          setCard(stored)
        } else {
          setNotFound(true)
          setCard(null)
          if (!silent) setPublicHistory(null)
        }
      } else {
        if (!isApiMode && isVerifiedPublicDemo) {
          const [hydrated] = await hydrateCachedAiDecisions([res])
          setCard(hydrated ?? res)
        } else {
          setCard(res)
        }
        if (isApiMode || isVerifiedPublicDemo) {
          void getRuntimeStatus().then((status) => {
            setRuntimeStatus(status)
            setRuntimeStatusChecked(true)
          })
        }
      }
    } catch (cause) {
      if (isAuthRequiredError(cause)) {
        navigate('/login', { replace: true })
        return
      }
      setError('商机详情加载失败，请稍后重试。')
    } finally {
      setLoading(false)
    }
  }, [id, navigate])

  useEffect(() => {
    void load()
  }, [load])

  const updateStatus = async (
    status: FollowupStatus,
    extra?: { reason?: string; note?: string; remind_at?: string },
  ) => {
    if (!card) return
    try {
      await todayActionsService.updateFollowup(card.opportunity_id, { status, ...extra })
      await load(true)
      toast(
        extra?.remind_at
          ? '提醒已设置，当前销售阶段保持不变'
          : historical
            ? '历史商机的私有跟进状态已更新；公开快照保持不变'
            : '跟进状态已更新',
        'success',
      )
    } catch (cause) {
      if (isAuthRequiredError(cause)) {
        navigate('/login', { replace: true })
        return
      }
      toast('跟进状态更新失败，请重试')
    }
  }

  const addNote = async (note: string): Promise<boolean> => {
    if (!card) return false
    const latestNotFitReason = card.followup_history.find(
      (item) => item.status === 'NOT_FIT' && Boolean(item.reason),
    )?.reason
    try {
      await todayActionsService.updateFollowup(card.opportunity_id, {
        status: card.followup_status,
        note,
        ...(card.followup_status === 'NOT_FIT' && latestNotFitReason
          ? { reason: latestNotFitReason }
          : {}),
      })
      await load(true)
      toast('跟进备注已保存', 'success')
      return true
    } catch (cause) {
      if (isAuthRequiredError(cause)) {
        navigate('/login', { replace: true })
        return false
      }
      toast('备注保存失败，请重试')
      return false
    }
  }

  const analyze = async () => {
    const automationUnavailableReason = runtimeAutomationUnavailableReason(
      runtimeStatus,
      runtimeStatusChecked,
    )
    if (!card || historical || automationUnavailableReason || (!isApiMode && !isVerifiedPublicDemo)) return
    setAiBusy(true)
    try {
      const decision = await requestAiDecision(card)
      setCard({
        ...card,
        model_decision_status: 'READY',
        model_block_reason: null,
        decision,
      })
      toast('AI行动建议已生成', 'success')
    } catch (cause) {
      if (cause instanceof AiDecisionError && cause.code === 'AUTH_REQUIRED') {
        navigate('/login', { replace: true })
        return
      }
      if (cause instanceof AiDecisionError && cause.code === 'AI_NOT_CONFIGURED') {
        setRuntimeStatus((current) =>
          current ? { ...current, ai: { configured: false } } : current,
        )
      }
      toast(aiDecisionErrorMessage(cause))
    } finally {
      setAiBusy(false)
    }
  }

  if (loading) return <LoadingState />
  if (error) return <ErrorState message={error} onRetry={() => void load()} />
  if (notFound || !card) {
    return (
      <EmptyState title="未找到该商机" hint="请返回今日行动或商机池，从当前商机进入详情。" />
    )
  }

  const buyerDisplay = card.facts.hospital ?? card.facts.buyer_name ?? null
  const automationUnavailableReason = historical
    ? null
    : runtimeAutomationUnavailableReason(runtimeStatus, runtimeStatusChecked)
  const snapshotWarning = historical
    ? null
    : runtimeSnapshotWarning(runtimeStatus, runtimeStatusChecked)
  const groundingUnavailable =
    card.model_decision_status === 'BLOCKED_GROUNDING' ||
    card.model_decision_status === 'NOT_ELIGIBLE' ||
    card.evidence_source_urls.length === 0
  const outreachDisabled = historical || groundingUnavailable || Boolean(automationUnavailableReason)
  const outreachDisabledReason = automationUnavailableReason ||
    (groundingUnavailable ? '公开依据不足，暂不能生成沟通草稿' : null)
  const aiUnavailableReason = automationUnavailableReason || (
    !historical && (isApiMode || isVerifiedPublicDemo) && runtimeStatus?.ai.configured === false
      ? AI_UNCONFIGURED_REASON
      : null
  )

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          to={historical ? '/followed' : '/today'}
          className="inline-flex items-center gap-1 text-[13px] text-slate-600 hover:text-slate-900"
        >
          <ArrowLeft className="h-4 w-4" />
          {historical ? '返回我的跟进' : '返回今日行动'}
        </Link>
        {!historical ? (
          <button
            type="button"
            disabled={outreachDisabled}
            title={outreachDisabled ? outreachDisabledReason || '暂不能生成沟通草稿' : undefined}
            onClick={() => {
              if (!outreachDisabled) setOutreachOpen(true)
            }}
            className="inline-flex items-center gap-1 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-[12px] font-medium text-indigo-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <MessageSquareText className="h-3.5 w-3.5" />
            {outreachDisabled ? '暂不能生成草稿' : '生成沟通草稿'}
          </button>
        ) : null}
      </div>

      {historical ? (
        <section className="flex items-start gap-2 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-[12px] leading-5 text-amber-900">
          <Archive className="mt-0.5 h-4 w-4 shrink-0" />
          <p>这是你当时保存的跟进快照。公开事实已经冻结，不重新计算优先级，也不生成新的 AI 建议；但你的私有跟进状态、结果、备注和提醒仍可继续维护。</p>
        </section>
      ) : null}

      {snapshotWarning ? (
        <section className="flex items-start gap-2 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-[12px] leading-5 text-amber-900">
          <Info className="mt-0.5 h-4 w-4 shrink-0" />
          <p>{snapshotWarning}</p>
        </section>
      ) : null}

      <section className="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
        <div className="flex flex-wrap items-center gap-2">
          {historical ? (
            <span className="rounded-md bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-800 ring-1 ring-amber-200">
              历史跟进快照
            </span>
          ) : (
            <>
              <span className="rounded-md bg-slate-900 px-2 py-0.5 text-[11px] font-semibold text-white">
                重点 {card.rank}
              </span>
              <PriorityBadge score={card.priority.score} scoreScope={card.priority.score_scope} />
              {card.facts.verification_status === 'VERIFIED' ? (
                <a
                  href="#official-evidence"
                  className="inline-flex items-center gap-1 rounded-full border border-teal-200 bg-teal-50 px-2 py-0.5 text-[11px] font-medium text-teal-800 hover:bg-teal-100"
                >
                  <ShieldCheck className="h-3 w-3" />
                  已核验官方事实 · {card.evidence_source_urls.length} 个依据
                </a>
              ) : null}
            </>
          )}
        </div>
        <h2 className="mt-2 text-lg font-semibold leading-7 text-slate-900">
          <OfficialText value={buyerDisplay} />
        </h2>
        <p className="mt-1 text-[14px] leading-6 text-slate-700">
          <OfficialText value={card.facts.project_name} />
        </p>
        <p className="mt-3 text-[12px] leading-5 text-slate-500">
          {historical
            ? '以下公开字段和官方链接来自进入跟进流程时保存的快照，不代表当前项目状态。'
            : '先决定怎么做，再按需查看官方事实、证据和评分解释。'}
        </p>
      </section>

      {!historical ? (
        <>
          <OpportunityExecutionCard card={card} onProfileChanged={() => load(true)} />
          <DecisionCard
            card={card}
            analyzing={aiBusy}
            onAnalyze={
              isApiMode || isVerifiedPublicDemo
                ? () => void analyze()
                : undefined
            }
            analysisUnavailableReason={aiUnavailableReason}
            analysisDisabled={Boolean(automationUnavailableReason)}
          />
        </>
      ) : null}

      <FollowupCard
        card={card}
        onChangeStatus={(status) => void updateStatus(status)}
        onAddNote={addNote}
        onWon={() => setWonOpen(true)}
        onNotFit={() => setNotFitOpen(true)}
        onLost={() => setLostOpen(true)}
        onRemind={() => setRemindOpen(true)}
      />

      <FactsCard facts={card.facts} />
      {isApiMode ? (
        <PublicHistoryCard
          history={publicHistory}
          loading={publicHistoryLoading}
          error={publicHistoryError}
          onLoad={() => loadPublicHistory(card.opportunity_id)}
        />
      ) : null}
      <div id="official-evidence" className="scroll-mt-20">
        <EvidenceCard
          urls={card.evidence_source_urls}
          verificationStatus={card.facts.verification_status}
        />
      </div>

      {!historical ? (
        <>
          <PriorityCard priority={card.priority} />
          <CustomerContextCard context={card.customer_context} />
        </>
      ) : null}

      <WonModal
        open={wonOpen}
        onClose={() => setWonOpen(false)}
        onConfirm={(reason: WonReason) => {
          setWonOpen(false)
          void updateStatus('WON', {
            note: `成交复盘（当前用户判断）：${reason}`,
          })
        }}
      />
      <NotFitModal
        open={notFitOpen}
        onClose={() => setNotFitOpen(false)}
        onConfirm={(reason: NotFitReason) => {
          setNotFitOpen(false)
          void updateStatus('NOT_FIT', { reason })
        }}
      />
      <LostModal
        open={lostOpen}
        onClose={() => setLostOpen(false)}
        onConfirm={(reason: LostReason) => {
          setLostOpen(false)
          void updateStatus('LOST', {
            note: `未成交原因（当前用户判断）：${reason}`,
          })
        }}
      />
      <RemindModal
        open={remindOpen}
        onClose={() => setRemindOpen(false)}
        onConfirm={(remindAt, nextAction) => {
          setRemindOpen(false)
          void updateStatus(card.followup_status, {
            remind_at: remindAt,
            note: nextAction
              ? `下次行动：${nextAction}`
              : '设置下次跟进提醒；销售阶段保持不变。',
          })
        }}
      />
      {!historical ? (
        <OutreachDrawer
          open={outreachOpen}
          opportunityId={card.opportunity_id}
          onClose={() => setOutreachOpen(false)}
        />
      ) : null}
    </div>
  )
}