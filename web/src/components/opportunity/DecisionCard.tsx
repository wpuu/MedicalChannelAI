import { Eye, Loader2, ShieldAlert, Sparkles } from 'lucide-react'
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
}

export function DecisionCard({ card, onAnalyze, analyzing }: DecisionCardProps) {
  const copy = MODEL_STATUS_COPY[card.model_decision_status]
  const hasCustomerContext = hasUserCustomerContext(card.customer_context)

  return (
    <SectionCard
      title="AI行动建议"
      subtitle={
        hasCustomerContext
          ? '已核验公开事实与用户确认资源分开使用；不预测中标概率'
          : '只基于已核验公开事实，不预测中标概率，不推断院内关系'
      }
      tone="ai"
      extra={
        <SourceTag tone="ai">
          {!isApiMode && isVerifiedPublicDemo
            ? hasCustomerContext
              ? '公开事实 + 我的资源'
              : '公开事实约束AI'
            : 'AI行动建议'}
        </SourceTag>
      }
    >
      {card.model_decision_status === 'READY' && card.decision ? (
        <div className="space-y-4">
          {!isApiMode && isVerifiedPublicDemo ? (
            <div className="rounded-xl border border-indigo-100 bg-indigo-50/60 px-3 py-2 text-[12px] leading-5 text-indigo-900">
              {hasCustomerContext
                ? '公开采购事实由服务端 VERIFIED 快照提供；“我的资源”来自你自己填写的业务信息。AI可以结合两者做行动判断，但不会把用户自述改写成医院官方事实。'
                : '本次分析只读取服务端已发布的 VERIFIED 快照。浏览器不能自行提交或修改“已核验事实”。'}
            </div>
          ) : null}
          <div>
            <p className="text-[12px] text-slate-500">建议动作</p>
            <p className="mt-1 flex items-start gap-1.5 text-[15px] font-semibold leading-6 text-slate-900">
              <Sparkles className="mt-1 h-4 w-4 shrink-0 text-indigo-600" />
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
            {card.decision.risks.length === 0 ? (
              <p className="mt-1 text-[13px] text-slate-500">当前信息下未补充额外风险；仍需人工核对正式附件与实际资源状态。</p>
            ) : (
              <ul className="mt-1 space-y-1.5">
                {card.decision.risks.map((item) => (
                  <li key={item} className="flex gap-2 text-[13px] leading-6 text-slate-700">
                    <span className="mt-[9px] h-1 w-1 shrink-0 rounded-full bg-amber-500" />
                    {item}
                  </li>
                ))}
              </ul>
            )}
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
        isApiMode ? (
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
            <Eye className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" />
            <div className="min-w-0 flex-1">
              <p className="text-[14px] font-semibold text-slate-800">尚未做AI行动分析</p>
              <p className="mt-1 text-[13px] leading-6 text-slate-500">
                {hasCustomerContext
                  ? '当前排序已经结合你填写的产品能力或医院关系。点击分析后，AI会把这些用户确认资源与服务端已核验公开事实分开使用，进一步给出行动建议。'
                  : '当前排序只使用已核验公开事实、项目金额和时间窗口。没有客户产品资料或医院关系时，系统不会假装已经完成资源匹配。'}
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
        )
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
