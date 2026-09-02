import { useEffect, useMemo, useState } from 'react'
import { CheckCircle2, ClipboardList, Layers3, Sparkles, Target } from 'lucide-react'
import type { TodayActionsResponse } from '@/types'
import { isApiMode } from '@/services/apiConfig'
import {
  loadRecommendationFeedback,
  subscribeRemoteRecommendationFeedback,
} from '@/services/recommendationFeedbackApi'
import {
  recommendationFeedbackSummary,
  subscribeOpportunityFeedback,
  type OpportunityFeedback,
} from '@/services/opportunityFeedbackStore'

const items = [
  {
    key: 'input_candidate_count',
    label: '已核验候选',
    icon: ClipboardList,
    hint: '进入事实筛选的公开项目',
    value: (data: TodayActionsResponse) => data.input_candidate_count,
  },
  {
    key: 'matched_count',
    label: '商机池',
    icon: Layers3,
    hint: '当前仍值得判断或跟进',
    value: (data: TodayActionsResponse) => data.matched_count,
  },
  {
    key: 'card_count',
    label: '今日重点',
    icon: Target,
    hint: '优先处理的前几条商机',
    value: (data: TodayActionsResponse) => data.card_count,
  },
  {
    key: 'ai_ready',
    label: '重点已分析',
    icon: CheckCircle2,
    hint: '今日重点中已有AI建议',
    value: (data: TodayActionsResponse) =>
      data.cards.filter((card) => card.model_decision_status === 'READY' && card.decision).length,
  },
]

interface SurpriseSummary {
  responded: number
  effective_surprises: number
  effective_surprise_rate: number | null
}

function summarize(values: Array<OpportunityFeedback | null>): SurpriseSummary {
  const responded = values.filter((value): value is OpportunityFeedback => value !== null)
  const effective = responded.filter((value) => value === 'NEW_WORTH_FOLLOWING').length
  return {
    responded: responded.length,
    effective_surprises: effective,
    effective_surprise_rate:
      responded.length > 0 ? Math.round((effective / responded.length) * 100) : null,
  }
}

function EffectiveSurpriseMetric({ opportunityIds }: { opportunityIds: string[] }) {
  const key = useMemo(() => [...new Set(opportunityIds)].sort().join('\n'), [opportunityIds])
  const ids = useMemo(() => key ? key.split('\n') : [], [key])
  const [summary, setSummary] = useState<SurpriseSummary>(() =>
    isApiMode ? { responded: 0, effective_surprises: 0, effective_surprise_rate: null } : recommendationFeedbackSummary(ids),
  )
  const [loading, setLoading] = useState(isApiMode)
  const [error, setError] = useState(false)

  useEffect(() => {
    let active = true
    let requestVersion = 0

    const refresh = () => {
      const version = ++requestVersion
      if (!isApiMode) {
        setSummary(recommendationFeedbackSummary(ids))
        setLoading(false)
        setError(false)
        return
      }
      setLoading(true)
      setError(false)
      void Promise.all(ids.map((id) => loadRecommendationFeedback(id)))
        .then((values) => {
          if (!active || version !== requestVersion) return
          setSummary(summarize(values))
          setLoading(false)
        })
        .catch(() => {
          if (!active || version !== requestVersion) return
          setError(true)
          setLoading(false)
        })
    }

    refresh()
    const unsubscribe = isApiMode
      ? subscribeRemoteRecommendationFeedback(refresh)
      : subscribeOpportunityFeedback(refresh)
    return () => {
      active = false
      unsubscribe()
    }
  }, [ids, key])

  const display = loading
    ? '…'
    : error || summary.effective_surprise_rate === null
      ? '—'
      : `${summary.effective_surprise_rate}%`
  const hint = loading
    ? '正在汇总当前商机反馈'
    : error
      ? '反馈统计暂时不可用'
      : summary.responded === 0
        ? '至少反馈1条后开始统计'
        : `${summary.effective_surprises}/${summary.responded} 条是“新且值得跟”`

  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-3 py-3 shadow-sm">
      <div className="flex items-center gap-1.5 text-slate-500">
        <Sparkles className="h-3.5 w-3.5" />
        <span className="text-[12px]">有效惊喜率</span>
      </div>
      <div className="mt-1.5 text-2xl font-semibold tabular-nums text-slate-900">{display}</div>
      <p className="mt-0.5 text-[11px] leading-4 text-slate-400">{hint}</p>
    </div>
  )
}

export function MetricCards({ data }: { data: TodayActionsResponse }) {
  const opportunityIds = (data.opportunity_pool?.length ? data.opportunity_pool : data.cards)
    .map((card) => card.opportunity_id)

  return (
    <div className="grid grid-cols-2 gap-2.5 md:grid-cols-5">
      {items.map((item) => {
        const Icon = item.icon
        return (
          <div
            key={item.key}
            className="rounded-2xl border border-slate-200 bg-white px-3 py-3 shadow-sm"
          >
            <div className="flex items-center gap-1.5 text-slate-500">
              <Icon className="h-3.5 w-3.5" />
              <span className="text-[12px]">{item.label}</span>
            </div>
            <div className="mt-1.5 text-2xl font-semibold tabular-nums text-slate-900">
              {item.value(data)}
            </div>
            <p className="mt-0.5 text-[11px] leading-4 text-slate-400">{item.hint}</p>
          </div>
        )
      })}
      <EffectiveSurpriseMetric opportunityIds={opportunityIds} />
    </div>
  )
}
