import { cn } from '@/utils/cn'
import { getPriorityLabel, getPriorityTier } from '@/utils/format'
import type { PriorityTier } from '@/types'

function publicSignalTier(score: number): PriorityTier {
  if (score >= 50) return 'critical'
  if (score >= 40) return 'high'
  if (score >= 30) return 'medium'
  return 'low'
}

function publicSignalLabel(score: number): string {
  if (score >= 50) return '公开信号强'
  if (score >= 40) return '值得查看'
  if (score >= 30) return '持续观察'
  return '低优先'
}

export function PriorityBadge({
  score,
  publicOnly,
}: {
  score: number
  publicOnly?: boolean
}) {
  const usePublicScale = publicOnly ?? score <= 60
  const tier = usePublicScale ? publicSignalTier(score) : getPriorityTier(score)
  const label = usePublicScale ? publicSignalLabel(score) : getPriorityLabel(score)
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

export function PriorityScore({
  score,
  publicOnly,
}: {
  score: number
  publicOnly?: boolean
}) {
  const usePublicScale = publicOnly ?? score <= 60
  const tier = usePublicScale ? publicSignalTier(score) : getPriorityTier(score)
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
      <span className="text-[11px] text-slate-400">
        {usePublicScale ? '/ 60 公开分' : '分'}
      </span>
    </div>
  )
}
