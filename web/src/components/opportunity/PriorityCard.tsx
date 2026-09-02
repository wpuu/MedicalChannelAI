import type { Priority } from '@/types'
import { SectionCard } from '@/components/shared/SectionCard'
import { PriorityBadge, PriorityScore } from '@/components/shared/PriorityBadge'
import { clampPercent } from '@/utils/format'
import { PRIORITY_COMPONENT_LABEL } from '@/utils/labels'

export function PriorityCard({ priority }: { priority: Priority }) {
  const usePublicScale = priority.score_scope !== 'PERSONALIZED'
  const entries = Object.entries(priority.components) as [keyof Priority['components'], number][]

  return (
    <SectionCard
      title="商机优先级"
      subtitle={usePublicScale ? '公开事实维度（满分60）' : '公开事实 + 当前账号私有资源（满分100）'}
      extra={<PriorityBadge score={priority.score} scoreScope={priority.score_scope} />}
    >
      <div className="mb-4 flex items-end justify-between gap-3">
        <div>
          <p className="text-[12px] text-slate-500">
            {usePublicScale ? '公开事实得分' : '个性化经营优先级'}
          </p>
          <PriorityScore score={priority.score} scoreScope={priority.score_scope} />
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
        {usePublicScale
          ? '当前为公开事实0–60分，不包含账号私有产品能力和医院关系。分项为各维度得分占比，不可直接相加。'
          : '当前为个性化0–100分，服务端已将当前账号与该商机相关的私有资源纳入排序。分项为各维度得分占比；总分用于安排销售资源优先级，不代表中标概率。'}
      </p>
    </SectionCard>
  )
}
