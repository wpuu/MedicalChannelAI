import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
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
import { useToast } from '@/context/ToastContext'
import { todayActionsService } from '@/services'
import type { FollowupStatus, NotFitReason, TodayActionCard } from '@/types'
import { OfficialText } from '@/components/shared/EmptyValue'

export function OpportunityDetailPage() {
  const { id } = useParams()
  const { toast } = useToast()
  const [card, setCard] = useState<TodayActionCard | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [notFitOpen, setNotFitOpen] = useState(false)
  const [outreachOpen, setOutreachOpen] = useState(false)

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
      } else {
        setCard(res)
      }
    } catch {
      setError('商机详情加载失败，请稍后重试。')
    } finally {
      setLoading(false)
    }
  }, [id])

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
      toast('演示模式：跟进状态已在本地更新', 'success')
    } catch {
      toast('本地更新失败，请重试')
    }
  }

  if (loading) return <LoadingState />
  if (error) return <ErrorState message={error} onRetry={() => void load()} />
  if (notFound || !card) {
    return (
      <EmptyState title="未找到该商机" hint="请返回今日行动，从当前 5 张卡片进入详情。" />
    )
  }

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
          onClick={() => setOutreachOpen(true)}
          className="inline-flex items-center gap-1 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-[12px] font-medium text-indigo-800"
        >
          <MessageSquareText className="h-3.5 w-3.5" />
          生成沟通话术
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
          <OfficialText value={card.facts.hospital} />
        </h2>
        <p className="mt-1 text-[14px] leading-6 text-slate-700">
          <OfficialText value={card.facts.project_name} />
        </p>
        <p className="mt-3 text-[12px] leading-5 text-slate-500">
          经营优先级，用于安排销售资源，不代表中标概率。
        </p>
      </section>

      <FactsCard facts={card.facts} />
      <EvidenceCard
        urls={card.evidence_source_urls}
        verificationStatus={card.facts.verification_status}
      />
      <CustomerContextCard context={card.customer_context} />
      <PriorityCard priority={card.priority} />
      <DecisionCard card={card} />
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
