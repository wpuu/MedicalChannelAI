import { Scale } from 'lucide-react'
import type { TodayActionCard } from '@/types'
import {
  COMPLAINT_RULE_NOTE,
  LEGAL_WINDOW_DISCLAIMER,
  legalWindowSummary,
} from '@/utils/legalWindows'

interface LegalWindowNoticeProps {
  card: Pick<TodayActionCard, 'legal_windows' | 'recommendation_mode'>
  /** Compact: a single line for list cards. Full: headline + legal basis + complaint rule. */
  compact?: boolean
}

/**
 * Renders the derived 质疑期 countdown. It is always labelled as an estimate
 * with unverified applicability/anchors and never shown as an official deadline. Closed windows
 * are shown only in the full variant so list cards stay quiet.
 */
export function LegalWindowNotice({ card, compact = false }: LegalWindowNoticeProps) {
  const summary = legalWindowSummary(card)
  if (!summary) return null
  const open = summary.status === 'OPEN' && summary.remaining > 0
  if (compact && summary.status === 'CLOSED') return null

  const tone = open
    ? summary.remaining <= 2
      ? 'border-rose-200 bg-rose-50 text-rose-900'
      : 'border-teal-200 bg-teal-50 text-teal-900'
    : 'border-slate-200 bg-slate-50 text-slate-600'

  if (compact) {
    return (
      <span
        className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${tone}`}
        title={LEGAL_WINDOW_DISCLAIMER}
      >
        <Scale className="h-3 w-3" />
        <span>{summary.headline}<span className="block font-normal">{LEGAL_WINDOW_DISCLAIMER}</span></span>
      </span>
    )
  }

  return (
    <div className={`rounded-lg border px-2.5 py-2 text-[11px] leading-5 ${tone}`}>
      <div className="flex items-start gap-1.5">
        <Scale className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <div className="min-w-0">
          <p className="font-medium">{summary.headline}</p>
          <p className="mt-0.5 opacity-90">{summary.basisNote}</p>
          {open ? <p className="mt-0.5 opacity-90">{COMPLAINT_RULE_NOTE}</p> : null}
          <p className="mt-0.5 opacity-75">
            {LEGAL_WINDOW_DISCLAIMER}
          </p>
        </div>
      </div>
    </div>
  )
}
