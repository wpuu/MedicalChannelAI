import { useState } from 'react'
import { CalendarClock, ChevronRight, Layers, Loader2, Sparkles, Users } from 'lucide-react'
import type { PageBrief } from '@/services/aiDecisionApi'
import { SourceTag } from '@/components/shared/StageBadge'

interface PageBriefPanelProps {
  brief: PageBrief | null
  regionLabel: string
  loading: boolean
  generating: boolean
  aiUnavailableReason: string | null
  aiError: string | null
  onGenerate?: () => void
  onOpen: (opportunityId: string) => void
}

function daysLeftText(days: number): string {
  if (days <= 0) return '今天'
  if (days === 1) return '明天'
  return `${days}天后`
}

/**
 * Whole-page brief: one combined judgement over every open opportunity of the
 * business region ("what first, what can wait"), instead of N separate
 * single-card analyses. Numbers are rendered from verified facts only.
 */
export function PageBriefPanel({
  brief,
  regionLabel,
  loading,
  generating,
  aiUnavailableReason,
  aiError,
  onGenerate,
  onOpen,
}: PageBriefPanelProps) {
  const [showSkip, setShowSkip] = useState(false)

  if (loading && !brief) {
    return (
      <section className="rounded-2xl border border-indigo-100 bg-white px-3 py-3 text-[12px] text-slate-500 shadow-sm sm:px-4">
        <span className="inline-flex items-center gap-1.5">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          正在整理{regionLabel}今日研判…
        </span>
      </section>
    )
  }
  if (!brief || brief.item_count === 0) return null

  const isAi = brief.brief_source === 'AI'
  const canGenerate = !isAi && Boolean(onGenerate)

  return (
    <section className="rounded-2xl border border-indigo-100 bg-white px-3 py-3 shadow-sm sm:px-4 sm:py-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 text-[15px] font-semibold text-slate-900">
            <Sparkles className="h-4 w-4 text-indigo-600" />
            今日研判 · {regionLabel}
          </p>
          <p className="mt-0.5 text-[12px] leading-5 text-slate-500">
            {isAi
              ? `AI一次比较了本地区全部 ${brief.item_count} 条可跟进商机`
              : `按官方截止、早期信号和预算对本地区 ${brief.item_count} 条可跟进商机排序`}
            {brief.early_signal_count > 0 ? `，其中早期信号 ${brief.early_signal_count} 条` : ''}
          </p>
        </div>
        <SourceTag tone="ai">{isAi ? 'AI整页研判' : '规则排序'}</SourceTag>
      </div>

      {brief.headline ? (
        <p className="mt-2 rounded-lg bg-indigo-50/60 px-2.5 py-2 text-[13px] font-medium leading-6 text-indigo-950">
          {brief.headline}
        </p>
      ) : null}

      <ol className="mt-3 space-y-2">
        {brief.focus.map((item, index) => (
          <li key={item.opportunity_id} className="rounded-xl border border-slate-200 px-3 py-2.5">
            <button
              type="button"
              onClick={() => onOpen(item.opportunity_id)}
              className="flex w-full items-start justify-between gap-2 text-left"
            >
              <span className="min-w-0">
                <span className="flex flex-wrap items-center gap-1.5">
                  <span className="rounded-md bg-slate-900 px-1.5 py-0.5 text-[11px] font-semibold text-white">
                    先做 {index + 1}
                  </span>
                  <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-900">
                    {item.reason_label}
                  </span>
                </span>
                <span className="mt-1 block text-[14px] font-semibold leading-6 text-slate-900">
                  {item.buyer_name ?? '采购人未公布'}
                </span>
                <span className="block break-words text-[13px] leading-5 text-slate-700">
                  {item.project_name}
                </span>
              </span>
              <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-slate-400" />
            </button>
            {item.fact_line ? (
              <p className="mt-1.5 text-[12px] leading-5 text-slate-600">{item.fact_line}</p>
            ) : null}
            {item.note ? (
              <p className="mt-1 text-[12px] leading-5 text-indigo-800">AI：{item.note}</p>
            ) : null}
            <p className="mt-1 text-[12px] leading-5 text-slate-500">下一步：{item.next_step}</p>
          </li>
        ))}
      </ol>

      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-[12px] leading-5 text-slate-600">
        {brief.deadlines_within_7_days.length > 0 ? (
          <span className="inline-flex items-center gap-1">
            <CalendarClock className="h-3.5 w-3.5 text-slate-400" />
            7天内官方截止 {brief.deadlines_within_7_days.length} 条（最近：
            {daysLeftText(brief.deadlines_within_7_days[0].days_left)}）
          </span>
        ) : null}
        {brief.same_buyer_groups.slice(0, 2).map((group) => (
          <span key={group.buyer_name} className="inline-flex items-center gap-1">
            <Users className="h-3.5 w-3.5 text-slate-400" />
            {group.buyer_name} 有 {group.count} 个项目，可一并跟进
          </span>
        ))}
      </div>

      {brief.skip.length > 0 ? (
        <div className="mt-2">
          <button
            type="button"
            onClick={() => setShowSkip((value) => !value)}
            className="inline-flex items-center gap-1 text-[12px] font-medium text-slate-600 hover:text-slate-900"
          >
            <Layers className="h-3.5 w-3.5" />
            可暂缓 {brief.skip.length} 条{showSkip ? '（收起）' : '（展开）'}
          </button>
          {showSkip ? (
            <ul className="mt-1.5 space-y-1 text-[12px] leading-5 text-slate-600">
              {brief.skip.map((item) => (
                <li key={item.opportunity_id}>
                  <button
                    type="button"
                    onClick={() => onOpen(item.opportunity_id)}
                    className="text-left hover:text-slate-900"
                  >
                    {item.buyer_name ?? '采购人未公布'} · {item.project_name}
                    <span className="ml-1 text-slate-400">— {item.reason_label}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      {canGenerate ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={generating || Boolean(aiUnavailableReason)}
            onClick={onGenerate}
            title={aiUnavailableReason || '把本地区全部可跟进商机整合成一次AI调用，比较后给出先做什么、可暂缓什么'}
            className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-[12px] font-medium text-indigo-800 hover:bg-indigo-100 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-500"
          >
            {generating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
            {generating ? `AI正在比较全部 ${brief.item_count} 条…` : `AI整页研判（一次分析全部 ${brief.item_count} 条）`}
          </button>
          {generating ? (
            <span className="text-[11px] text-slate-500">通常10–20秒，今天其他人再打开会直接看到结果</span>
          ) : aiError ? (
            <span className="text-[11px] text-amber-700">AI暂未给出可通过校验的结果，当前显示规则排序</span>
          ) : aiUnavailableReason ? (
            <span className="text-[11px] text-amber-700">{aiUnavailableReason}</span>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
