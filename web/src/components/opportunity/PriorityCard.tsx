import type { Priority } from '@/types'
import { SectionCard } from '@/components/shared/SectionCard'
import { PriorityBadge, PriorityScore } from '@/components/shared/PriorityBadge'
import { clampPercent } from '@/utils/format'
import { PRIORITY_COMPONENT_LABEL } from '@/utils/labels'

export function PriorityCard({
  priority,
  publicOnly = false,
}: {
  priority: Priority
  publicOnly?: boolean
}) {
  const entries = Object.entries(priority.components) as [keyof Priority['components'], number][]

  return (
    <SectionCard
      title="商机优先级"
      subtitle={publicOnly ? '公开事实优先级，尚未计入你的资源匹配' : '为什么排在前面'}
      extra={<PriorityBadge score={priority.score} publicOnly={publicOnly} />}
    >
      <div className="mb-4 flex items-end justify-between gap-3">
        <div>
          <p className="text-[12px] text-slate-500">
            {publicOnly ? '公开事实得分' : '经营优先级'}
          </p>
          <PriorityScore score={priority.score} publicOnly={publicOnly} />
        </div>
      </div>
      <div className="space-y-3">
        {entries.map(([key, value]) => (
          <div key={key}>
            <div className="mb-1 flex items-center justify-between text-[12px]">
              <span className="text-slate-600">{PRIORITY_COMPONENT_LABEL[key]}</span>
              <span className="tabular-nums text-slate-500">{value}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-teal-700"
                style={{ width: `${clampPercent(value)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
      <p className="mt-4 rounded-lg bg-slate-50 px-3 py-2 text-[12px] leading-5 text-slate-500">
        {publicOnly
          ? '当前仅按公开事实计算，满分60；填写产品能力、医院关系和执行方式后，才进入满分100的个性化经营优先级。分项为各维度得分占比，不可直接相加。'
          : '分项显示的是各维度得分占比，用于解释强弱，不可直接相加；总分用于安排销售资源优先级，不代表中标概率。'}
      </p>
    </SectionCard>
  )
}
