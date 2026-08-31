import { Eye, Loader2, ShieldAlert, Sparkles } from 'lucide-react'
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
}

export function DecisionBlock({ card, onAnalyze, analyzing }: DecisionBlockProps) {
  const copy = MODEL_STATUS_COPY[card.model_decision_status]
  const hasCustomerContext = hasUserCustomerContext(card.customer_context)

  if (card.model_decision_status === 'READY' && card.decision) {
    return (
      <div className="rounded-xl border border-indigo-100 bg-indigo-50/40 p-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <p className="flex items-center gap-1.5 text-[13px] font-semibold text-indigo-950">
            <Sparkles className="h-3.5 w-3.5" />
            AI行动建议
          </p>
          <SourceTag tone="ai">
            {!isApiMode && isVerifiedPublicDemo
              ? hasCustomerContext
                ? '公开事实 + 我的资源'
                : '公开事实约束AI'
              : 'AI判断'}
          </SourceTag>
        </div>
        {!isApiMode && isVerifiedPublicDemo ? (
          <p className="mb-2 rounded-lg bg-white/70 px-2.5 py-2 text-[11px] leading-5 text-indigo-800">
            {hasCustomerContext
              ? '本次AI使用服务端已核验公开事实，并结合你在“我的资源”中自行确认的产品能力或医院关系；两类信息保持独立来源，不把用户自述升级成医院官方事实。'
              : '本次AI只使用服务端已核验公开事实；未填写客户资源时，不推断医院关系、厂家授权或产品能力。'}
          </p>
        ) : null}
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
            <div className="min-w-0 flex-1">
              <p className="text-[13px] font-semibold text-slate-800">尚未做AI行动分析</p>
              <p className="mt-1 text-[12px] leading-5 text-slate-500">
                {hasCustomerContext
                  ? '当前经营优先级已结合你填写的产品能力或医院关系。点击分析后，AI会把这些用户确认资源与服务端已核验公开事实分开使用，给出更具体的下一步动作。'
                  : '当前只按已核验公开事实、项目金额和时间窗口排序；未录入客户产品能力或医院关系，因此不推断产品匹配度、中标概率或院内关系。'}
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
                      : '用AI分析这条'}
                </button>
              ) : null}
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
