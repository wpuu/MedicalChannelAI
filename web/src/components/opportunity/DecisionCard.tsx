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
  analysisDisabled?: boolean
}

export function DecisionCard({
  card,
  onAnalyze,
  analyzing,
  analysisUnavailableReason,
  analysisDisabled,
}: DecisionCardProps) {
  const copy = MODEL_STATUS_COPY[card.model_decision_status]
  const hasCustomerContext = hasUserCustomerContext(card.customer_context)

  return (
    <SectionCard
      title="下一步行动"
      subtitle={
        isApiMode
          ? hasCustomerContext
            ? '已核验公开事实 + 当前账号已确认资源，按固定规则生成'
            : '按已核验公开事实的固定规则生成'
          : hasCustomerContext
            ? '结合公开信息和我的资源，按固定规则生成'
            : '按已核验公开信息的固定规则生成'
      }
      tone="ai"
      extra={
        <SourceTag tone="ai">
          {isApiMode
            ? hasCustomerContext
              ? '公开事实 + 账号资源'
              : '已核验公开事实'
            : isVerifiedPublicDemo
              ? hasCustomerContext
                ? '公开信息 + 我的资源'
                : '公开信息'
              : '规则生成'}
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
        <div>
          <p className="text-[13px] leading-6 text-slate-500">
            {isApiMode
              ? hasCustomerContext
                ? '按已核验公开事实生成；账号私有资源由服务器按当前用户和当前商机最小化读取。'
                : '按已核验公开事实生成，不会替你猜测医院关系或产品资源。'
              : hasCustomerContext
                ? '结合这条商机和你的资源，生成下一步动作。'
                : '按这条公开商机生成下一步动作和需要确认的事项。'}
          </p>
          {onAnalyze ? (
            <button
              type="button"
              disabled={Boolean(analyzing) || analysisDisabled}
              onClick={onAnalyze}
              className="mt-3 inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-[12px] font-medium text-indigo-800 transition hover:bg-indigo-100 disabled:cursor-not-allowed disabled:opacity-50"
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
                    : analysisUnavailableReason
                      ? '重试'
                      : '生成下一步'}
            </button>
          ) : null}
          {analysisUnavailableReason ? (
            <p className="mt-2 text-[11px] leading-5 text-amber-700">
              {analysisUnavailableReason}
            </p>
          ) : null}
        </div>
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
