import { useCallback, useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import {
  getPrivateOutcomeSummary,
  type PrivateOutcomeSummary,
} from '@/services/outcomeSummaryApi'

function ReasonList({
  title,
  items,
  unclassified,
}: {
  title: string
  items: PrivateOutcomeSummary['lost_reason_counts']
  unclassified: number
}) {
  if (!items.length && !unclassified) return null
  return (
    <div className="rounded-xl bg-slate-50 px-3 py-3">
      <p className="text-[12px] font-medium text-slate-700">{title}</p>
      <div className="mt-2 space-y-1.5">
        {items.slice(0, 5).map((item) => (
          <div key={item.code} className="flex items-center justify-between gap-3 text-[12px]">
            <span className="min-w-0 text-slate-600">{item.label}</span>
            <span className="shrink-0 font-medium tabular-nums text-slate-800">{item.count}</span>
          </div>
        ))}
        {unclassified ? (
          <div className="flex items-center justify-between gap-3 text-[12px]">
            <span className="min-w-0 text-slate-500">历史未结构化</span>
            <span className="shrink-0 font-medium tabular-nums text-slate-700">{unclassified}</span>
          </div>
        ) : null}
      </div>
    </div>
  )
}

export function OutcomeSummaryCard() {
  const [summary, setSummary] = useState<PrivateOutcomeSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      setSummary(await getPrivateOutcomeSummary())
    } catch {
      setSummary(null)
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  if (loading) return null
  if (error) {
    return (
      <section className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-[12px] font-medium text-slate-700">私有结果复盘暂不可用</p>
            <p className="mt-0.5 text-[11px] text-slate-400">不影响跟进列表和日常推进，可单独重试。</p>
          </div>
          <button
            type="button"
            onClick={() => void load()}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-[12px] text-slate-600"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            重试
          </button>
        </div>
      </section>
    )
  }
  if (!summary?.total_terminal) return null

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-[14px] font-semibold text-slate-900">私有结果复盘</h3>
          <p className="mt-1 max-w-3xl text-[11px] leading-5 text-slate-500">
            只统计当前账号已结束的私有跟进结果；不写入公开商机事实，也不自动改变公共机会排序。
          </p>
        </div>
        <span className="rounded-full bg-slate-50 px-2 py-1 text-[10px] text-slate-500 ring-1 ring-slate-200">
          当前账号私有
        </span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[
          ['已成交', summary.won],
          ['未成交', summary.lost],
          ['不适合', summary.not_fit],
          [
            '已决成交率',
            summary.win_rate_percent === null ? '—' : `${summary.win_rate_percent}%`,
          ],
        ].map(([label, value]) => (
          <div key={String(label)} className="rounded-xl border border-slate-100 px-3 py-2.5">
            <p className="text-[10px] text-slate-400">{label}</p>
            <p className="mt-0.5 text-lg font-semibold tabular-nums text-slate-900">{value}</p>
          </div>
        ))}
      </div>
      <p className="mt-2 text-[10px] leading-4 text-slate-400">
        “已决成交率”仅按 已成交 ÷（已成交 + 未成交）计算；“不适合”不进入该分母。
      </p>

      {summary.lost_reason_counts.length ||
      summary.not_fit_reason_counts.length ||
      summary.unclassified_lost ||
      summary.unclassified_not_fit ? (
        <div className="mt-3 grid gap-2 md:grid-cols-2">
          <ReasonList
            title="未成交主要原因"
            items={summary.lost_reason_counts}
            unclassified={summary.unclassified_lost}
          />
          <ReasonList
            title="不适合主要原因"
            items={summary.not_fit_reason_counts}
            unclassified={summary.unclassified_not_fit}
          />
        </div>
      ) : null}
    </section>
  )
}
