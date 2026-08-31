import { useEffect, useMemo, useState } from 'react'
import { ExternalLink, Filter, Search, SlidersHorizontal } from 'lucide-react'
import { EmptyState, ErrorState, LoadingState } from '@/components/shared/PageStates'
import { PriorityBadge } from '@/components/shared/PriorityBadge'
import { StageBadge } from '@/components/shared/StageBadge'
import { getVerifiedOpportunityPool } from '@/services/verifiedOpportunityPool'
import type { TodayActionCard } from '@/types'
import { formatBudget, formatDateTime } from '@/utils/format'

type WindowFilter = 'ALL' | 'OPEN' | 'LATE_WINDOW'

function normalizedSearchText(card: TodayActionCard): string {
  return [
    card.facts.project_code,
    card.facts.project_name,
    card.facts.hospital,
    card.facts.buyer_name,
    card.facts.department,
    card.facts.region,
    ...(card.facts.product_categories ?? []),
    ...(card.facts.products ?? []).flatMap((item) => [item.name, item.category, item.specification]),
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
}

function deadlineLabel(card: TodayActionCard): string | null {
  if (card.facts.bid_deadline) {
    const formatted = formatDateTime(card.facts.bid_deadline)
    return formatted ? `投标/响应截止 ${formatted}` : null
  }
  if (card.facts.registration_deadline) {
    const formatted = formatDateTime(card.facts.registration_deadline)
    return formatted ? `报名截止 ${formatted}` : null
  }
  return null
}

function PoolCard({ card }: { card: TodayActionCard }) {
  const buyer = card.facts.hospital ?? card.facts.buyer_name ?? '采购单位未提供'
  const budget = formatBudget(card.facts.budget)
  const deadline = deadlineLabel(card)
  const late = card.recommendation_mode === 'LATE_WINDOW'

  return (
    <article className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3 px-4 py-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-md bg-slate-900 px-2 py-0.5 text-[11px] font-semibold text-white">
              #{card.rank}
            </span>
            <PriorityBadge score={card.priority.score} />
            <StageBadge stage={card.facts.lifecycle_stage} />
            {late ? (
              <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-800">
                报名窗口已结束
              </span>
            ) : null}
          </div>
          <h3 className="mt-2 text-[15px] font-semibold leading-6 text-slate-900">{buyer}</h3>
          <p className="mt-0.5 text-[14px] leading-6 text-slate-700">
            {card.facts.project_name ?? '项目名称未提供'}
          </p>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-slate-500">
            {budget ? <span>公开预算 {budget}</span> : <span>公开预算未提供</span>}
            {deadline ? <span>{deadline}</span> : null}
            {card.facts.region ? <span>{card.facts.region}</span> : null}
          </div>
        </div>
        <div className="shrink-0 text-right">
          <div className="text-2xl font-semibold tabular-nums text-slate-900">{card.priority.score}</div>
          <div className="text-[11px] text-slate-400">经营优先级</div>
        </div>
      </div>

      <details className="border-t border-slate-100 px-4 py-3">
        <summary className="cursor-pointer select-none text-[12px] font-medium text-teal-700">
          查看设备、联系人和官方依据
        </summary>
        <div className="mt-3 grid gap-4 text-[12px] leading-5 text-slate-600 md:grid-cols-2">
          <div>
            <p className="font-medium text-slate-800">采购内容</p>
            {card.facts.products?.length ? (
              <ul className="mt-1 space-y-1">
                {card.facts.products.slice(0, 12).map((item, index) => (
                  <li key={`${item.name}-${index}`}>• {item.name}</li>
                ))}
                {card.facts.products.length > 12 ? (
                  <li className="text-slate-400">另有 {card.facts.products.length - 12} 项</li>
                ) : null}
              </ul>
            ) : card.facts.product_categories?.length ? (
              <p className="mt-1">{card.facts.product_categories.join('、')}</p>
            ) : (
              <p className="mt-1 text-slate-400">公开页面未结构化出设备明细</p>
            )}
          </div>
          <div>
            <p className="font-medium text-slate-800">公开联系人</p>
            {card.facts.official_contact ? (
              <div className="mt-1 space-y-0.5">
                {card.facts.official_contact.name ? <p>{card.facts.official_contact.name}</p> : null}
                {card.facts.official_contact.title ? <p>{card.facts.official_contact.title}</p> : null}
                {card.facts.official_contact.phone ? <p>{card.facts.official_contact.phone}</p> : null}
                {card.facts.official_contact.email ? <p>{card.facts.official_contact.email}</p> : null}
              </div>
            ) : (
              <p className="mt-1 text-slate-400">当前公开事实未提供联系人</p>
            )}
            <div className="mt-3 flex flex-wrap gap-2">
              {card.evidence_source_urls.map((url, index) => (
                <a
                  key={url}
                  href={url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-[11px] font-medium text-slate-700 hover:bg-slate-100"
                >
                  官方依据 {index + 1}
                  <ExternalLink className="h-3 w-3" />
                </a>
              ))}
            </div>
          </div>
        </div>
      </details>
    </article>
  )
}

export function OpportunityPoolPage() {
  const [cards, setCards] = useState<TodayActionCard[]>([])
  const [snapshotAsOf, setSnapshotAsOf] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [windowFilter, setWindowFilter] = useState<WindowFilter>('ALL')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    void getVerifiedOpportunityPool()
      .then((result) => {
        if (cancelled) return
        setCards(result.cards)
        setSnapshotAsOf(result.snapshot_as_of)
        setError(false)
      })
      .catch(() => {
        if (!cancelled) setError(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return cards.filter((card) => {
      if (windowFilter === 'OPEN' && card.recommendation_mode === 'LATE_WINDOW') return false
      if (windowFilter === 'LATE_WINDOW' && card.recommendation_mode !== 'LATE_WINDOW') return false
      if (!needle) return true
      return normalizedSearchText(card).includes(needle)
    })
  }, [cards, query, windowFilter])

  if (loading) return <LoadingState />
  if (error) {
    return <ErrorState message="商机池加载失败，请稍后重试。" onRetry={() => window.location.reload()} />
  }

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">全部已核验商机</h2>
            <p className="mt-1 text-[13px] leading-6 text-slate-500">
              今日行动只展示 Top 5；这里保留同一事实快照中全部仍有效的公开机会。
            </p>
          </div>
          <div className="text-[12px] text-slate-500">
            {snapshotAsOf ? `快照 ${formatDateTime(snapshotAsOf) ?? snapshotAsOf}` : null}
          </div>
        </div>

        <div className="mt-4 flex flex-col gap-2 sm:flex-row">
          <label className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索医院、项目、设备、科室..."
              className="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 pl-9 pr-3 text-[13px] outline-none focus:border-teal-400 focus:bg-white"
            />
          </label>
          <div className="flex items-center gap-1 rounded-xl border border-slate-200 bg-slate-50 p-1">
            <SlidersHorizontal className="ml-2 h-3.5 w-3.5 text-slate-400" />
            {([
              ['ALL', '全部'],
              ['OPEN', '窗口开放'],
              ['LATE_WINDOW', '晚窗口'],
            ] as const).map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => setWindowFilter(value)}
                className={`rounded-lg px-2.5 py-1.5 text-[12px] font-medium ${
                  windowFilter === value ? 'bg-white text-teal-800 shadow-sm' : 'text-slate-500'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-3 flex items-center gap-1.5 text-[12px] text-slate-500">
          <Filter className="h-3.5 w-3.5" />
          当前显示 {visible.length} / {cards.length} 条
        </div>
      </section>

      {visible.length ? (
        <div className="space-y-3">
          {visible.map((card) => (
            <PoolCard key={card.opportunity_id} card={card} />
          ))}
        </div>
      ) : (
        <EmptyState title="没有符合条件的商机" hint="可以清空搜索词或切换筛选条件。" />
      )}
    </div>
  )
}
