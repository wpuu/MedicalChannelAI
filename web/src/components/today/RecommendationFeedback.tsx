import { useEffect, useState, useSyncExternalStore } from 'react'
import { isApiMode } from '@/services/apiConfig'
import {
  getOpportunityFeedback,
  setOpportunityFeedback,
  subscribeOpportunityFeedback,
  type OpportunityFeedback,
} from '@/services/opportunityFeedbackStore'
import {
  loadRecommendationFeedback,
  saveRecommendationFeedback,
} from '@/services/recommendationFeedbackApi'

const OPTIONS: Array<{ value: OpportunityFeedback; label: string }> = [
  { value: 'ALREADY_KNOWN', label: '早就知道' },
  { value: 'NEW_NOT_VALUABLE', label: '新，但没价值' },
  { value: 'NEW_WORTH_FOLLOWING', label: '新，而且值得跟' },
]

interface RecommendationFeedbackProps {
  opportunityId: string
  onWorthFollowing?: () => void
  onFeedbackChanged?: (value: OpportunityFeedback | null) => Promise<void> | void
}

export function RecommendationFeedback({
  opportunityId,
  onWorthFollowing,
  onFeedbackChanged,
}: RecommendationFeedbackProps) {
  const localSelected = useSyncExternalStore(
    subscribeOpportunityFeedback,
    () => getOpportunityFeedback(opportunityId),
    () => null,
  )
  const [remoteSelected, setRemoteSelected] = useState<OpportunityFeedback | null>(null)
  const [remoteLoaded, setRemoteLoaded] = useState(!isApiMode)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!isApiMode) return
    let active = true
    setRemoteLoaded(false)
    setError(false)
    setRemoteSelected(null)
    void loadRecommendationFeedback(opportunityId)
      .then((value) => {
        if (!active) return
        setRemoteSelected(value)
        setRemoteLoaded(true)
      })
      .catch(() => {
        if (!active) return
        setError(true)
        setRemoteLoaded(true)
      })
    return () => { active = false }
  }, [opportunityId])

  const selected = isApiMode ? remoteSelected : localSelected

  const choose = async (value: OpportunityFeedback) => {
    if (saving || (isApiMode && !remoteLoaded)) return
    const previous = selected
    const next = selected === value ? null : value
    setError(false)

    if (!isApiMode) {
      setOpportunityFeedback(opportunityId, next)
      if (next === 'NEW_WORTH_FOLLOWING' && previous !== 'NEW_WORTH_FOLLOWING') {
        onWorthFollowing?.()
      }
      await onFeedbackChanged?.(next)
      return
    }

    setRemoteSelected(next)
    setSaving(true)
    try {
      const confirmed = await saveRecommendationFeedback(opportunityId, next)
      setRemoteSelected(confirmed)
      if (confirmed === 'NEW_WORTH_FOLLOWING' && previous !== 'NEW_WORTH_FOLLOWING') {
        onWorthFollowing?.()
      }
      await onFeedbackChanged?.(confirmed)
    } catch {
      setRemoteSelected(previous)
      setError(true)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="border-t border-slate-100 px-3 py-2.5 sm:px-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <div>
          <p className="text-[11px] leading-5 text-slate-500">
            这条推荐对你？反馈不改变业务优先级分；尚未跟进的“没价值”项目会退出今日队列，“早就知道”会降低新发现优先级。
          </p>
          {isApiMode && !remoteLoaded ? (
            <p className="text-[10px] leading-4 text-slate-400">正在读取账号反馈…</p>
          ) : null}
          {error ? (
            <p className="text-[10px] leading-4 text-rose-600">反馈同步失败，未覆盖账号中的原记录。</p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {OPTIONS.map((option) => {
            const active = selected === option.value
            return (
              <button
                key={option.value}
                type="button"
                aria-pressed={active}
                disabled={saving || (isApiMode && !remoteLoaded)}
                onClick={() => void choose(option.value)}
                className={
                  active
                    ? 'rounded-full border border-teal-300 bg-teal-50 px-2.5 py-1 text-[11px] font-medium text-teal-800 disabled:opacity-60'
                    : 'rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[11px] text-slate-600 hover:bg-slate-50 disabled:opacity-50'
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
