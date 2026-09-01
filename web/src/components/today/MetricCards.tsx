import { CheckCircle2, ClipboardList, Layers3, Target } from 'lucide-react'
import type { TodayActionsResponse } from '@/types'

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

export function MetricCards({ data }: { data: TodayActionsResponse }) {
  return (
    <div className="grid grid-cols-2 gap-2.5 md:grid-cols-4">
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
    </div>
  )
}
