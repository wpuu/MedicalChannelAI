import { useEffect, useMemo, useState } from 'react'
import { CheckCircle2, ClipboardList, Layers3, Radar, Sparkles, Target } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import type { RecommendationFeedbackSummary, TodayActionsResponse } from '@/types'
import { isApiMode } from '@/services/apiConfig'
import {
  recommendationFeedbackSummary,
  subscribeOpportunityFeedback,
} from '@/services/opportunityFeedbackStore'
import { updateTodayLimit } from '@/services/todayDisplayPreferenceApi'

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
    key: 'early_signal_count',
    label: '早期信号',
    icon: CheckCircle2,
    hint: '采购意向等正式招标前的信号',
    value: (data: TodayActionsResponse) =>
      (data.opportunity_pool ?? data.cards).filter(
        (card) => card.facts.lifecycle_stage === 'PROCUREMENT_INTENT',
      ).length,
  },
]

type SurpriseSummary = RecommendationFeedbackSummary

function ProcurementIntentFormalAlert({ data }: { data: TodayActionsResponse }) {
  const navigate = useNavigate()
  const summary = data.procurement_intent_followup_summary
  if (!summary) return null
  const pendingCount = summary.formal_candidates_needing_action ?? summary.intents_with_formal_successor
  if (pendingCount <= 0) return null

  return (
    <button
      type="button"
      onClick={() => navigate('/intent-followup')}
      className="flex w-full items-start justify-between gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 px-3 py-3 text-left shadow-sm hover:bg-emerald-100/70 sm:px-4"
    >
      <div className="flex min-w-0 items-start gap-2.5">
        <Radar className="mt-0.5 h-4 w-4 shrink-0 text-emerald-700" />
        <div className="min-w-0">
          <p className="text-[13px] font-semibold leading-5 text-emerald-950">
            {pendingCount} 个可能的正式窗口待核查
          </p>
          <p className="mt-0.5 text-[11px] leading-5 text-emerald-800">
            {summary.intents_with_formal_successor} 条采购意向已出现可能的正式窗口，当前共发现 {summary.candidate_pair_count} 组保守关联候选；这里只提醒尚未显式处理的正式候选。关联只依据公开事实自动提示，公开关联结论不因私有跟进状态改变，仍需人工核对，不代表官方确认同一项目。
          </p>
        </div>
      </div>
      <span className="shrink-0 rounded-lg bg-white px-2.5 py-1.5 text-[11px] font-medium text-emerald-800 ring-1 ring-emerald-200">
        立即核查
      </span>
    </button>
  )
}

function SurpriseMetricView({
  summary,
  loading = false,
  error = false,
}: {
  summary: SurpriseSummary
  loading?: boolean
  error?: boolean
}) {
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

function LocalEffectiveSurpriseMetric({ opportunityIds }: { opportunityIds: string[] }) {
  const key = useMemo(() => [...new Set(opportunityIds)].sort().join('\n'), [opportunityIds])
  const ids = useMemo(() => key ? key.split('\n') : [], [key])
  const [summary, setSummary] = useState<SurpriseSummary>(() => recommendationFeedbackSummary(ids))

  useEffect(() => {
    const refresh = () => setSummary(recommendationFeedbackSummary(ids))
    refresh()
    return subscribeOpportunityFeedback(refresh)
  }, [ids, key])

  return <SurpriseMetricView summary={summary} />
}

function EffectiveSurpriseMetric({
  opportunityIds,
  serverSummary,
}: {
  opportunityIds: string[]
  serverSummary?: RecommendationFeedbackSummary
}) {
  if (isApiMode) {
    return (
      <SurpriseMetricView
        summary={serverSummary ?? {
          responded: 0,
          effective_surprises: 0,
          effective_surprise_rate: null,
        }}
        error={!serverSummary}
      />
    )
  }
  return <LocalEffectiveSurpriseMetric opportunityIds={opportunityIds} />
}

function TodayLimitControl({ data }: { data: TodayActionsResponse }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)
  const current = data.today_limit
  const options = data.today_limit_options?.filter((value) => Number.isInteger(value) && value > 0) ?? []

  if (!isApiMode || !current || options.length === 0) return null

  const changeLimit = async (value: number) => {
    if (value === current || busy) return
    setBusy(true)
    setError(false)
    try {
      await updateTodayLimit(value)
      window.location.reload()
    } catch {
      setError(true)
      setBusy(false)
    }
  }

  return (
    <div className="mt-2 border-t border-slate-100 pt-2">
      <label className="flex items-center justify-between gap-2 text-[11px] text-slate-500">
        <span>首页显示</span>
        <select
          value={current}
          disabled={busy}
          onChange={(event) => void changeLimit(Number(event.target.value))}
          className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-[11px] text-slate-700 disabled:opacity-60"
          aria-label="今日重点显示数量"
        >
          {options.map((value) => (
            <option key={value} value={value}>{value} 条</option>
          ))}
        </select>
      </label>
      {error ? <p className="mt-1 text-[10px] text-rose-600">保存失败，请重试</p> : null}
    </div>
  )
}

export function MetricCards({ data }: { data: TodayActionsResponse }) {
  const opportunityIds = (data.opportunity_pool?.length ? data.opportunity_pool : data.cards)
    .map((card) => card.opportunity_id)

  return (
    <div className="space-y-2.5">
      <ProcurementIntentFormalAlert data={data} />
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
              {item.key === 'card_count' ? <TodayLimitControl data={data} /> : null}
            </div>
          )
        })}
        <EffectiveSurpriseMetric
          opportunityIds={opportunityIds}
          serverSummary={data.recommendation_feedback_summary}
        />
      </div>
    </div>
  )
}