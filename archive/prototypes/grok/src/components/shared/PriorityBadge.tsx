import { cn } from '@/utils/cn'
import { getPriorityLabel, getPriorityTier } from '@/utils/format'

export function PriorityBadge({ score }: { score: number }) {
  const tier = getPriorityTier(score)
  const label = getPriorityLabel(score)
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2 py-0.5 text-[12px] font-medium',
        tier === 'critical' && 'border-rose-200 bg-rose-50 text-rose-800',
        tier === 'high' && 'border-amber-200 bg-amber-50 text-amber-800',
        tier === 'medium' && 'border-sky-200 bg-sky-50 text-sky-800',
        tier === 'low' && 'border-slate-200 bg-slate-50 text-slate-600',
      )}
    >
      {label}
    </span>
  )
}

export function PriorityScore({ score }: { score: number }) {
  const tier = getPriorityTier(score)
  return (
    <div className="flex items-baseline gap-1">
      <span
        className={cn(
          'text-xl font-semibold tabular-nums',
          tier === 'critical' && 'text-rose-800',
          tier === 'high' && 'text-amber-800',
          tier === 'medium' && 'text-sky-800',
          tier === 'low' && 'text-slate-600',
        )}
      >
        {score}
      </span>
      <span className="text-[11px] text-slate-400">分</span>
    </div>
  )
}
