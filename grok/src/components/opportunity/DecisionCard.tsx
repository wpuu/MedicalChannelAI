import { Loader2, ShieldAlert, Sparkles } from 'lucide-react'
import type { TodayActionCard } from '@/types'
import { SectionCard } from '@/components/shared/SectionCard'
import { SourceTag } from '@/components/shared/StageBadge'
import { MODEL_STATUS_COPY } from '@/utils/labels'

export function DecisionCard({ card }: { card: TodayActionCard }) {
  const copy = MODEL_STATUS_COPY[card.model_decision_status]

  return (
    <SectionCard
      title="AI行动建议"
      subtitle="只基于已经提供的信息，不预测医院一定会采购"
      tone="ai"
      extra={<SourceTag tone="ai">AI行动建议</SourceTag>}
    >
      {card.model_decision_status === 'READY' && card.decision ? (
        <div className="space-y-4">
          <div>
            <p className="text-[12px] text-slate-500">建议动作</p>
            <p className="mt-1 flex items-center gap-1.5 text-[15px] font-semibold text-slate-900">
              <Sparkles className="h-4 w-4 text-indigo-600" />
              {card.decision.action}
            </p>
          </div>
          <div>
            <p className="text-[12px] font-medium text-slate-500">判断原因</p>
            <ul className="mt-1 space-y-1.5">
              {card.decision.reasons.map((item) => (
                <li key={item} className="flex gap-2 text-[13px] leading-6 text-slate-700">
                  <span className="mt-[9px] h-1 w-1 shrink-0 rounded-full bg-indigo-400" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="text-[12px] font-medium text-slate-500">风险</p>
            <ul className="mt-1 space-y-1.5">
              {card.decision.risks.map((item) => (
                <li key={item} className="flex gap-2 text-[13px] leading-6 text-slate-700">
                  <span className="mt-[9px] h-1 w-1 shrink-0 rounded-full bg-amber-500" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <p className="text-[12px] font-medium text-slate-500">需要人工确认</p>
            {card.decision.needs_human_confirmation.length === 0 ? (
              <p className="mt-1 text-[13px] text-slate-500">暂无</p>
            ) : (
              <ul className="mt-1 space-y-1.5">
                {card.decision.needs_human_confirmation.map((item) => (
                  <li key={item} className="flex gap-2 text-[13px] leading-6 text-slate-700">
                    <span className="mt-[9px] h-1 w-1 shrink-0 rounded-full bg-slate-400" />
                    {item}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ) : card.model_decision_status === 'AWAITING_MODEL' ? (
        <div>
          <div className="flex items-center gap-2 text-[14px] font-semibold text-indigo-900">
            <Loader2 className="h-4 w-4 animate-spin" />
            AI分析排队中
          </div>
          <div className="mt-3 space-y-2">
            <div className="h-3 w-3/4 animate-pulse-soft rounded bg-indigo-100" />
            <div className="h-3 w-full animate-pulse-soft rounded bg-indigo-100" />
            <div className="h-3 w-1/2 animate-pulse-soft rounded bg-indigo-100" />
          </div>
          <p className="mt-3 text-[12px] leading-5 text-slate-500">{copy.hint}</p>
        </div>
      ) : (
        <div className="flex items-start gap-2">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" />
          <div>
            <p className="text-[14px] font-semibold text-slate-800">{copy.title}</p>
            <p className="mt-1 text-[13px] leading-6 text-slate-500">{copy.hint}</p>
            {card.model_block_reason ? (
              <p className="mt-2 rounded-lg bg-white px-3 py-2 text-[12px] leading-5 text-slate-600">
                {card.model_block_reason}
              </p>
            ) : null}
          </div>
        </div>
      )}
    </SectionCard>
  )
}
