import { Building2, Calendar, Wallet } from 'lucide-react'
import type { TodayActionCard } from '@/types'
import { formatBudget, pickDisplayDate } from '@/utils/format'
import { FOLLOWUP_STATUS_LABEL } from '@/utils/labels'
import { OfficialText } from '@/components/shared/EmptyValue'
import { FollowupChip, SourceTag, StageBadge } from '@/components/shared/StageBadge'
import { PriorityBadge, PriorityScore } from '@/components/shared/PriorityBadge'
import { ActionButtons } from './ActionButtons'
import { CustomerResourceBlock } from './CustomerResourceBlock'
import { DecisionBlock } from './DecisionBlock'

interface ActionCardProps {
  card: TodayActionCard
  busy?: boolean
  onDetail: () => void
  onContacted: () => void
  onFollow: () => void
  onNotFit: () => void
  onRemind: () => void
  onOutreach: () => void
}

export function ActionCard({
  card,
  busy,
  onDetail,
  onContacted,
  onFollow,
  onNotFit,
  onRemind,
  onOutreach,
}: ActionCardProps) {
  const dateInfo = pickDisplayDate(card.facts)
  const budget = formatBudget(card.facts.budget)
  const buyerDisplay = card.facts.hospital ?? card.facts.buyer_name ?? null
  const outreachDisabled =
    card.model_decision_status === 'BLOCKED_GROUNDING' || card.evidence_source_urls.length === 0

  return (
    <article className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="rounded-md bg-slate-900 px-2 py-0.5 text-[11px] font-semibold tracking-wide text-white">
            TOP {card.rank}
          </span>
          <PriorityScore score={card.priority.score} />
          <PriorityBadge score={card.priority.score} />
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {card.followup_status !== 'NEW' ? (
            <FollowupChip label={FOLLOWUP_STATUS_LABEL[card.followup_status]} />
          ) : null}
          {card.facts.coverage_status === 'PARTIAL' ? (
            <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] text-amber-800">
              公开数据覆盖有限
            </span>
          ) : null}
        </div>
      </div>

      <div className="grid gap-3 px-4 py-4 lg:grid-cols-2">
        <div className="min-w-0 space-y-3">
          <div>
            <div className="mb-1 flex items-center gap-1.5">
              <SourceTag tone="official">官方/已验证事实</SourceTag>
            </div>
            <div className="flex items-start gap-2">
              <Building2 className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />
              <div className="min-w-0">
                <p className="text-[15px] font-semibold leading-6 text-slate-900">
                  <OfficialText value={buyerDisplay} />
                </p>
                <p className="mt-0.5 break-words text-[14px] leading-6 text-slate-700">
                  <OfficialText value={card.facts.project_name} />
                </p>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-[12px] text-slate-600">
              <StageBadge stage={card.facts.lifecycle_stage} />
              <span className="inline-flex items-center gap-1">
                <Wallet className="h-3.5 w-3.5 text-slate-400" />
                {budget ? `预算 ${budget}` : <OfficialText value={null} />}
              </span>
              <span className="inline-flex items-center gap-1">
                <Calendar className="h-3.5 w-3.5 text-slate-400" />
                {dateInfo ? (
                  `${dateInfo.label} ${dateInfo.value}`
                ) : (
                  <OfficialText value={null} />
                )}
              </span>
            </div>
          </div>
          <CustomerResourceBlock context={card.customer_context} />
        </div>
        <DecisionBlock card={card} />
      </div>

      <div className="border-t border-slate-100 px-4 py-3">
        <ActionButtons
          busy={busy}
          outreachDisabled={outreachDisabled}
          onDetail={onDetail}
          onContacted={onContacted}
          onFollow={onFollow}
          onNotFit={onNotFit}
          onRemind={onRemind}
          onOutreach={onOutreach}
        />
      </div>
    </article>
  )
}
