import { Eye, Loader2, ShieldAlert, Sparkles } from 'lucide-react'
import type { TodayActionCard } from '@/types'
import { MODEL_STATUS_COPY } from '@/utils/labels'
import { SourceTag } from '@/components/shared/StageBadge'
import { isApiMode } from '@/services/apiConfig'

export function DecisionBlock({ card }: { card: TodayActionCard }) {
  const copy = MODEL_STATUS_COPY[card.model_decision_status]

  if (card.model_decision_status === 'READY' && card.decision) {
    return (
      <div className="rounded-xl border border-indigo-100 bg-indigo-50/40 p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <p className="flex items-center gap-1.5 text-[13px] font-semibold text-indigo-950">
            <Sparkles className="h-3.5 w-3.5" />
            AI行动建议
          </p>
          <SourceTag tone="ai">AI判断</SourceTag>
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
            <p className="text-[12px] font-medium text-slate-500">风险</p>
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
    if (!isApiMode) {
      return (
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
          <div className="flex items-start gap-2">
            <Eye className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" />
            <div>
              <p className="text-[13px] font-semibold text-slate-800">当前先观察</p>
              <p className="mt-1 text-[12px] leading-5 text-slate-500">
                演示模式不模拟一个永远排队的模型任务。该项目产品匹配，但医院关系尚未确认，当前先保留观察。
              </p>
            </div>
          </div>
        </div>
      )
    }
    return (
      <div className="rounded-xl border border-indigo-100 bg-indigo-50/30 p-3">
        <div className="flex items-center gap-2 text-[13px] font-semibold text-indigo-900">
          <Loader2 className="h-4 w-4 animate-spin" />
          AI分析排队中
        </div>
        <div className="mt-3 space-y-2">
          <div className="h-3 w-3/4 animate-pulse-soft rounded bg-indigo-100" />
          <div className="h-3 w-full animate-pulse-soft rounded bg-indigo-100" />
          <div className="h-3 w-2/3 animate-pulse-soft rounded bg-indigo-100" />
        </div>
        <p className="mt-2 text-[12px] leading-5 text-slate-500">{copy.hint}</p>
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
