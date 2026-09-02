import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Archive, MessageSquareText, ShieldCheck } from 'lucide-react'
import { CustomerContextCard } from '@/components/opportunity/CustomerContextCard'
import { DecisionCard } from '@/components/opportunity/DecisionCard'
import { EvidenceCard } from '@/components/opportunity/EvidenceCard'
import { FactsCard } from '@/components/opportunity/FactsCard'
import { FollowupCard } from '@/components/opportunity/FollowupCard'
import { OpportunityExecutionCard } from '@/components/opportunity/OpportunityExecutionCard'
import { PriorityCard } from '@/components/opportunity/PriorityCard'
import { EmptyState, ErrorState, LoadingState } from '@/components/shared/PageStates'
import { PriorityBadge } from '@/components/shared/PriorityBadge'
import { NotFitModal } from '@/components/followup/NotFitModal'
import { RemindModal } from '@/components/followup/RemindModal'
import { OutreachDrawer } from '@/components/followup/OutreachDrawer'
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
import { getStoredHistoricalOpportunityCard } from '@/services/localFollowupStore'
import { getRuntimeStatus, type RuntimeStatus } from '@/services/runtimeStatusApi'
import type { FollowupStatus, NotFitReason, TodayActionCard } from '@/types'

const AI_UNCONFIGURED_REASON = 'AI暂时不可用，可稍后重试；其他功能正常。'

export function OpportunityDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { toast } = useToast()
  const [card, setCard] = useState<TodayActionCard | null>(null)
  const [historical, setHistorical] = useState(false)
  const [runtimeStatus, setRuntimeStatus] = useState<RuntimeStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [notFitOpen, setNotFitOpen] = useState(false)
  const [remindOpen, setRemindOpen] = useState(false)
  const [outreachOpen, setOutreachOpen] = useState(false)
  const [aiBusy, setAiBusy] = useState(false)

  const load = useCallback(async (silent = false) => {
    if (!id) {
      setNotFound(true)
      setLoading(false)
      return
    }
    if (!silent) {
      setLoading(true)
      setError(null)
    }
    setNotFound(false)
    setHistorical(false)
    try {
      const res = await todayActionsService.getOpportunity(id)
      if (!res) {
        const stored = !isApiMode && isVerifiedPublicDemo
          ? getStoredHistoricalOpportunityCard(id)
          : null
        if (stored) {
          setHistorical(true)
          setCard(stored)
        } else {
          setNotFound(true)
          setCard(null)
        }
      } else if (!isApiMode && isVerifiedPublicDemo) {
        const [hydrated] = await hydrateCachedAiDecisions([res])
        setCard(hydrated ?? res)
        void getRuntimeStatus().then((status) => {
          if (status) setRuntimeStatus(status)
        })
      } else {
        setCard(res)
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
    if (!card || historical) return
    try {
      await todayActionsService.updateFollowup(card.opportunity_id, { status, ...extra })
      await load(true)
      toast('跟进状态已更新', 'success')
    } catch (cause) {
      if (isAuthRequiredError(cause)) {
        navigate('/login', { replace: true })
        return
      }
      toast('跟进状态更新失败，请重试')
    }
  }

  const analyze = async () => {
    if (!card || historical || (!isApiMode && !isVerifiedPublicDemo)) return
    setAiBusy(true)
    try {
      const decision = await requestAiDecision(card)
      setRuntimeStatus((current) =>
        current ? { ...current, ai: { configured: true } } : current,
      )
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
  const outreachDisabled =
    historical ||
    card.model_decision_status === 'BLOCKED_GROUNDING' ||
    card.model_decision_status === 'NOT_ELIGIBLE' ||
    card.evidence_source_urls.length === 0
  const aiUnavailableReason =
    !historical && !isApiMode && isVerifiedPublicDemo && runtimeStatus?.ai.configured === false
      ? AI_UNCONFIGURED_REASON
      : null

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
            title={outreachDisabled ? '公开依据不足，暂不能生成沟通草稿' : undefined}
            onClick={() => setOutreachOpen(true)}
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
          <p>这是历史跟进快照，仅保留当时的公开信息和跟进记录。</p>
        </section>
      ) : null}

      <section className="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
        <div className="flex flex-wrap items-center gap-2">
          {historical ? (
            <span className="rounded-md bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-800 ring-1 ring-amber-200">
              历史快照
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
            ? '项目是否仍可介入请以当前官方信息为准。'
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
          />
          <FollowupCard
            card={card}
            onChangeStatus={(status) => void updateStatus(status)}
            onNotFit={() => setNotFitOpen(true)}
            onRemind={() => setRemindOpen(true)}
          />
        </>
      ) : null}

      <FactsCard facts={card.facts} />
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
      ) : (
        <FollowupCard
          card={card}
          readOnly
          onChangeStatus={() => undefined}
          onNotFit={() => undefined}
          onRemind={() => undefined}
        />
      )}

      {!historical ? (
        <>
          <NotFitModal
            open={notFitOpen}
            onClose={() => setNotFitOpen(false)}
            onConfirm={(reason: NotFitReason) => {
              setNotFitOpen(false)
              void updateStatus('NOT_FIT', { reason })
            }}
          />
          <RemindModal
            open={remindOpen}
            onClose={() => setRemindOpen(false)}
            onConfirm={(remindAt) => {
              setRemindOpen(false)
              void updateStatus('MONITOR', { remind_at: remindAt })
            }}
          />
          <OutreachDrawer
            open={outreachOpen}
            opportunityId={card.opportunity_id}
            onClose={() => setOutreachOpen(false)}
          />
        </>
      ) : null}
    </div>
  )
}
