import { useSyncExternalStore } from 'react'
import {
  getOpportunityFeedback,
  setOpportunityFeedback,
  subscribeOpportunityFeedback,
  type OpportunityFeedback,
} from '@/services/opportunityFeedbackStore'

const OPTIONS: Array<{ value: OpportunityFeedback; label: string }> = [
  { value: 'ALREADY_KNOWN', label: '早就知道' },
  { value: 'NEW_NOT_VALUABLE', label: '新，但没价值' },
  { value: 'NEW_WORTH_FOLLOWING', label: '新，而且值得跟' },
]

interface RecommendationFeedbackProps {
  opportunityId: string
  onWorthFollowing?: () => void
}

export function RecommendationFeedback({
  opportunityId,
  onWorthFollowing,
}: RecommendationFeedbackProps) {
  const selected = useSyncExternalStore(
    subscribeOpportunityFeedback,
    () => getOpportunityFeedback(opportunityId),
    () => null,
  )

  const choose = (value: OpportunityFeedback) => {
    const next = selected === value ? null : value
    setOpportunityFeedback(opportunityId, next)
    if (next === 'NEW_WORTH_FOLLOWING' && selected !== 'NEW_WORTH_FOLLOWING') {
      onWorthFollowing?.()
    }
  }

  return (
    <div className="border-t border-slate-100 px-3 py-2.5 sm:px-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <p className="text-[11px] leading-5 text-slate-500">
          这条推荐对你？反馈只用于改进推荐质量，不改变官方事实。
        </p>
        <div className="flex flex-wrap gap-1.5">
          {OPTIONS.map((option) => {
            const active = selected === option.value
            return (
              <button
                key={option.value}
                type="button"
                aria-pressed={active}
                onClick={() => choose(option.value)}
                className={
                  active
                    ? 'rounded-full border border-teal-300 bg-teal-50 px-2.5 py-1 text-[11px] font-medium text-teal-800'
                    : 'rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[11px] text-slate-600 hover:bg-slate-50'
                }
              >
                {option.label}
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
