import { ClipboardList, GitCompare, Loader, Target } from 'lucide-react'
import type { TodayActionsResponse } from '@/types'

const items = [
  {
    key: 'input_candidate_count' as const,
    label: '今日候选',
    icon: ClipboardList,
    hint: '进入筛选的公开项目',
  },
  {
    key: 'matched_count' as const,
    label: '匹配商机',
    icon: GitCompare,
    hint: '与客户资源匹配',
  },
  {
    key: 'card_count' as const,
    label: '今日重点',
    icon: Target,
    hint: '建议今天采取行动',
  },
  {
    key: 'model_request_count' as const,
    label: 'AI待分析',
    icon: Loader,
    hint: '等待行动建议',
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
              {data[item.key]}
            </div>
            <p className="mt-0.5 text-[11px] text-slate-400">{item.hint}</p>
          </div>
        )
      })}
    </div>
  )
}
