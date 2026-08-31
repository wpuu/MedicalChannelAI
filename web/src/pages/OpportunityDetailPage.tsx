import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, MessageSquareText } from 'lucide-react'
import { CustomerContextCard } from '@/components/opportunity/CustomerContextCard'
import { DecisionCard } from '@/components/opportunity/DecisionCard'
import { EvidenceCard } from '@/components/opportunity/EvidenceCard'
import { FactsCard } from '@/components/opportunity/FactsCard'
import { FollowupCard } from '@/components/opportunity/FollowupCard'
import { PriorityCard } from '@/components/opportunity/PriorityCard'
import { EmptyState, ErrorState, LoadingState } from '@/components/shared/PageStates'
import { PriorityBadge } from '@/components/shared/PriorityBadge'
import { NotFitModal } from '@/components/followup/NotFitModal'
import { OutreachDrawer } from '@/components/followup/OutreachDrawer'
import { OfficialText } from '@/components/shared/EmptyValue'
import { isVerifiedPublicDemo } from '@/config/demoDataset'
import { useToast } from '@/context/ToastContext'
import { todayActionsService } from '@/services'
import {
  AiDecisionError,
  hydrateCachedAiDecisions,
  requestAiDecision,
} from '@/services/aiDecisionApi'
import { isApiMode, isAuthRequiredError } from '@/services/apiConfig'
import type { FollowupStatus, NotFitReason, TodayActionCard } from '@/types'

function aiErrorMessage(cause: unknown): string {
  if (!(cause instanceof AiDecisionError)) return 'AI分析暂时不可用，请稍后重试'
  if (cause.code === 'AI_NOT_CONFIGURED') return 'AI服务端运行配置尚未完成'
  if (cause.code === 'AI_RATE_LIMITED') return 'AI服务当前限流，请稍后再试'
  if (cause.code === 'AI_PROVIDER_AUTH_UNAVAILABLE') return 'AI服务端当前不可用'
  if (cause.code === 'AI_TIMEOUT') return 'AI分析超时，请稍后重试'
  if (cause.code === 'VERIFIED_OPPORTUNITY_NOT_FOUND') return '该商机不在服务端已核验快照中，暂不能分析'
  return 'AI分析暂时不可用，请稍后重试'
}

export function OpportunityDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { toast } = useToast()
  const [card, setCard] = useState<TodayActionCard | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [notFitOpen, setNotFitOpen] = useState(false)
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
    try {
      const res = await todayActionsService.getOpportunity(id)
      if (!res) {
        setNotFound(true)
        setCard(null)
      } else if (!isApiMode && isVerifiedPublicDemo) {
        const [hydrated] = await hydrateCachedAiDecisions([res])
        setCard(hydrated ?? res)
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
    extra?: { reason?: string; note?: string },
  ) => {
    if (!card) return
    try {
      await todayActionsService.updateFollowup(card.opportunity_id, { status, ...extra })
      await load(true)
      toast(
        isApiMode ? '跟进状态已同步服务器' : '试用模式：跟进状态已在本地更新',
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

  const analyze = async () => {
    if (!card || isApiMode || !isVerifiedPublicDemo) return
    setAiBusy(true)
    try {
      const decision = await requestAiDecision(card)
      setCard({
        ...card,
        model_decision_status: 'READY',
        model_block_reason: null,
        decision,
      })
      toast('AI已基于已核验公开事实给出行动建议', 'success')
    } catch (cause) {
      toast(aiErrorMessage(cause))
    } finally {
      setAiBusy(false)
    }
  }

  if (loading) return <LoadingState />
  if (error) return <ErrorState message={error} onRetry={() => void load()} />
  if (notFound || !card) {
    return (
      <EmptyState title="未找到该商机" hint="请返回今日行动，从当前重点商机进入详情。" />
    )
  }

  const buyerDisplay = card.facts.hospital ?? card.facts.buyer_name ?? null
  const outreachDisabled =
    card.model_decision_status === 'BLOCKED_GROUNDING' ||
    card.model_decision_status === 'NOT_ELIGIBLE' ||
    card.evidence_source_urls.length === 0

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          to="/today"
          className="inline-flex items-center gap-1 text-[13px] text-slate-600 hover:text-slate-900"
        >
          <ArrowLeft className="h-4 w-4" />
          返回今日行动
        </Link>
        <button
          type="button"
          disabled={outreachDisabled}
          title={outreachDisabled ? '公开依据不足，暂不安全生成沟通草稿' : undefined}
          onClick={() => setOutreachOpen(true)}
          className="inline-flex items-center gap-1 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-[12px] font-medium text-indigo-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <MessageSquareText className="h-3.5 w-3.5" />
          {outreachDisabled ? '依据不足，暂不生成' : '生成沟通草稿'}
        </button>
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-md bg-slate-900 px-2 py-0.5 text-[11px] font-semibold text-white">
            TOP {card.rank}
          </span>
          <PriorityBadge score={card.priority.score} />
        </div>
        <h2 className="mt-2 text-lg font-semibold leading-7 text-slate-900">
          <OfficialText value={buyerDisplay} />
        </h2>
        <p className="mt-1 text-[14px] leading-6 text-slate-700">
          <OfficialText value={card.facts.project_name} />
        </p>
        <p className="mt-3 text-[12px] leading-5 text-slate-500">
          经营优先级用于安排销售资源，不代表中标概率；未录入客户资源时不判断医院关系或产品匹配度。
        </p>
      </section>

      <FactsCard facts={card.facts} />
      <EvidenceCard
        urls={card.evidence_source_urls}
        verificationStatus={card.facts.verification_status}
      />
      <CustomerContextCard context={card.customer_context} />
      <PriorityCard priority={card.priority} />
      <DecisionCard
        card={card}
        analyzing={aiBusy}
        onAnalyze={!isApiMode && isVerifiedPublicDemo ? () => void analyze() : undefined}
      />
      <FollowupCard
        card={card}
        onChangeStatus={(status) => void updateStatus(status)}
        onNotFit={() => setNotFitOpen(true)}
      />

      <NotFitModal
        open={notFitOpen}
        onClose={() => setNotFitOpen(false)}
        onConfirm={(reason: NotFitReason) => {
          setNotFitOpen(false)
          void updateStatus('NOT_FIT', { reason })
        }}
      />
      <OutreachDrawer
        open={outreachOpen}
        opportunityId={card.opportunity_id}
        onClose={() => setOutreachOpen(false)}
      />
    </div>
  )
}
