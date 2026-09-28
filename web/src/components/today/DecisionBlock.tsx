import { useEffect, useState } from 'react'
import { Loader2, ShieldAlert, Sparkles } from 'lucide-react'
import type { TodayActionCard } from '@/types'
import { MODEL_STATUS_COPY } from '@/utils/labels'
import { hasUserCustomerContext } from '@/utils/customerContext'
import { SourceTag } from '@/components/shared/StageBadge'
import { isVerifiedPublicDemo } from '@/config/demoDataset'
import { isApiMode } from '@/services/apiConfig'

interface DecisionBlockProps {
  card: TodayActionCard
  onAnalyze?: () => void
  analyzing?: boolean
  analysisUnavailableReason?: string | null
  analysisDisabled?: boolean
}

const SLOW_ANALYSIS_HINT_MS = 10_000

function useSlowAnalysisHint(analyzing: boolean): boolean {
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    if (!analyzing) {
      setSlow(false)
      return
    }
    const timer = setTimeout(() => setSlow(true), SLOW_ANALYSIS_HINT_MS)
    return () => clearTimeout(timer)
  }, [analyzing])
  return slow
}

export function DecisionBlock({
  card,
  onAnalyze,
  analyzing,
  analysisUnavailableReason,
  analysisDisabled,
}: DecisionBlockProps) {
  const copy = MODEL_STATUS_COPY[card.model_decision_status]
  const hasCustomerContext = hasUserCustomerContext(card.customer_context)
  const slowAnalysis = useSlowAnalysisHint(Boolean(analyzing))

  if (card.model_decision_status === 'READY' && card.decision) {
    return (
      <div className="rounded-xl border border-indigo-100 bg-indigo-50/40 p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <p className="flex items-center gap-1.5 text-[13px] font-semibold text-indigo-950">
            <Sparkles className="h-3.5 w-3.5" />
            下一步行动
          </p>
          <SourceTag tone="ai">
            {isApiMode
              ? hasCustomerContext
                ? '公开事实 + 账号资源'
                : '按已核验事实规则生成'
              : isVerifiedPublicDemo
                ? hasCustomerContext
                  ? '公开信息 + 我的资源'
                  : '按公开事实规则生成'
                : '规则生成'}
          </SourceTag>
        </div>
        <p className="text-[13px] leading-6 text-slate-800">
          建议动作
          <span className="ml-2 font-semibold">{card.decision.action}</span>
        </p>
        <div className="mt-2">
          <p className="text-[12px] font-medium text-slate-500">为什么</p>
          <ul className="mt-1 space-y-1 text-[13px] leading-5 text-slate-700">
            {card.decision.reasons.map((reason) => (
              <li key={reason} className="flex gap-2">
                <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-indigo-400" />
                <span>{reason}</span>
              </li>
            ))}
          </ul>
        </div>
        {card.decision.risks.length > 0 ? (
          <div className="mt-2">
            <p className="text-[12px] font-medium text-slate-500">需要确认</p>
            <ul className="mt-1 space-y-1 text-[13px] leading-5 text-slate-700">
              {card.decision.risks.map((risk) => (
                <li key={risk} className="flex gap-2">
                  <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-amber-500" />
                  <span>{risk}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    )
  }

  if (card.model_decision_status === 'AWAITING_MODEL') {
    return (
      <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
        <div className="min-w-0">
          <p className="text-[13px] font-semibold text-slate-800">下一步行动</p>
          <p className="mt-1 text-[12px] leading-5 text-slate-500">
            {hasCustomerContext
              ? '按已核验公开事实和你已确认的资源，用固定规则生成下一步动作。'
              : '按这条商机的已核验公开事实，用固定规则生成下一步动作和需要确认的事项。'}
          </p>
          {onAnalyze ? (
            <button
              type="button"
              disabled={Boolean(analyzing) || analysisDisabled}
              onClick={onAnalyze}
              className="mt-3 inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-[12px] font-medium text-indigo-800 transition hover:bg-indigo-100 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-500 disabled:opacity-70"
            >
              {analyzing ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Sparkles className="h-3.5 w-3.5" />
              )}
              {analyzing
                ? '生成中'
                : analysisDisabled
                  ? '暂不能生成'
                  : hasCustomerContext
                    ? '结合我的资源生成'
                    : '生成下一步'}
            </button>
          ) : null}
          {analyzing && slowAnalysis ? (
            <p className="mt-2 text-[11px] leading-5 text-slate-500">
              网络响应较慢，系统仍在继续处理，无需重复点击。
            </p>
          ) : analysisUnavailableReason ? (
            <p className="mt-2 text-[11px] leading-5 text-amber-700">
              {analysisUnavailableReason}
            </p>
          ) : null}
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
      <div className="flex items-start gap-2">
        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" />
        <div>
          <p className="text-[13px] font-semibold text-slate-800">{copy.title}</p>
          <p className="mt-1 text-[12px] leading-5 text-slate-500">{copy.hint}</p>
          {card.model_block_reason ? (
            <p className="mt-2 text-[12px] leading-5 text-slate-600">
              {card.model_block_reason}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  )
}
