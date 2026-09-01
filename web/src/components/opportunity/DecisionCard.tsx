import { Loader2, ShieldAlert, Sparkles } from 'lucide-react'
import type { TodayActionCard } from '@/types'
import { SectionCard } from '@/components/shared/SectionCard'
import { SourceTag } from '@/components/shared/StageBadge'
import { MODEL_STATUS_COPY } from '@/utils/labels'
import { hasUserCustomerContext } from '@/utils/customerContext'
import { isVerifiedPublicDemo } from '@/config/demoDataset'
import { isApiMode } from '@/services/apiConfig'

interface DecisionCardProps {
  card: TodayActionCard
  onAnalyze?: () => void
  analyzing?: boolean
  analysisUnavailableReason?: string | null
}

export function DecisionCard({
  card,
  onAnalyze,
  analyzing,
  analysisUnavailableReason,
}: DecisionCardProps) {
  const copy = MODEL_STATUS_COPY[card.model_decision_status]
  const hasCustomerContext = hasUserCustomerContext(card.customer_context)

  return (
    <SectionCard
      title="AI行动建议"
      subtitle={hasCustomerContext ? '结合公开信息和我的资源' : '基于已核验公开信息'}
      tone="ai"
      extra={
        <SourceTag tone="ai">
          {!isApiMode && isVerifiedPublicDemo
            ? hasCustomerContext
              ? '公开信息 + 我的资源'
              : '公开信息'
            : 'AI行动建议'}
        </SourceTag>
      }
    >
      {card.model_decision_status === 'READY' && card.decision ? (
        <div className="space-y-4">
          <div>
            <p className="text-[12px] text-slate-500">建议动作</p>
            <p className="mt-1 flex items-start gap-1.5 text-[15px] font-semibold leading-6 text-slate-900">
              <Sparkles className="mt-1 h-4 w-4 shrink-0 text-indigo-600" />
              {card.decision.action}
            </p>
          </div>
          <div>
            <p className="text-[12px] font-medium text-slate-500">为什么</p>
            <ul className="mt-1 space-y-1.5">
              {card.decision.reasons.map((item) => (
                <li key={item} className="flex gap-2 text-[13px] leading-6 text-slate-700">
                  <span className="mt-[9px] h-1 w-1 shrink-0 rounded-full bg-indigo-400" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
          {card.decision.risks.length > 0 ? (
            <div>
              <p className="text-[12px] font-medium text-slate-500">需要确认</p>
              <ul className="mt-1 space-y-1.5">
                {card.decision.risks.map((item) => (
                  <li key={item} className="flex gap-2 text-[13px] leading-6 text-slate-700">
                    <span className="mt-[9px] h-1 w-1 shrink-0 rounded-full bg-amber-500" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : card.model_decision_status === 'AWAITING_MODEL' ? (
        isApiMode ? (
          <div>
            <div className="flex items-center gap-2 text-[14px] font-semibold text-indigo-900">
              <Loader2 className="h-4 w-4 animate-spin" />
              AI分析中
            </div>
            <div className="mt-3 space-y-2">
              <div className="h-3 w-3/4 animate-pulse-soft rounded bg-indigo-100" />
              <div className="h-3 w-full animate-pulse-soft rounded bg-indigo-100" />
              <div className="h-3 w-1/2 animate-pulse-soft rounded bg-indigo-100" />
            </div>
          </div>
        ) : (
          <div>
            <p className="text-[13px] leading-6 text-slate-500">
              {hasCustomerContext
                ? '让AI结合这条商机和你的资源，给出下一步动作。'
                : '让AI基于这条公开商机，给出下一步动作和需要确认的事项。'}
            </p>
            {onAnalyze ? (
              <button
                type="button"
                disabled={analyzing}
                onClick={onAnalyze}
                className="mt-3 inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-[12px] font-medium text-indigo-800 transition hover:bg-indigo-100 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {analyzing ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Sparkles className="h-3.5 w-3.5" />
                )}
                {analyzing
                  ? 'AI分析中'
                  : hasCustomerContext
                    ? '结合我的资源分析'
                    : analysisUnavailableReason
                      ? '重试AI分析'
                      : '用AI分析这条'}
              </button>
            ) : null}
            {analysisUnavailableReason ? (
              <p className="mt-2 text-[11px] leading-5 text-amber-700">
                {analysisUnavailableReason}
              </p>
            ) : null}
          </div>
        )
      ) : (
        <div className="flex items-start gap-2">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" />
          <div>
            <p className="text-[14px] font-semibold text-slate-800">{copy.title}</p>
            <p className="mt-1 text-[13px] leading-6 text-slate-500">{copy.hint}</p>
            {card.model_block_reason ? (
              <p className="mt-2 text-[12px] leading-5 text-slate-600">
                {card.model_block_reason}
              </p>
            ) : null}
          </div>
        </div>
      )}
    </SectionCard>
  )
}
