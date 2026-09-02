import { useCallback, useEffect, useMemo, useState } from 'react'
import { ChevronRight, ExternalLink, Filter, RefreshCw, Search } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { EmptyState, ErrorState, LoadingState } from '@/components/shared/PageStates'
import { isAuthRequiredError } from '@/services/apiConfig'
import {
  getFollowedOpportunityById,
  getFollowedOpportunityPage,
  getFollowedStatusIndex,
  type FollowedOpportunity,
  type FollowedStatusIndexItem,
} from '@/services/followedApi'
import { formatBudget, formatDate, formatDateTime } from '@/utils/format'

const STATUS_LABELS: Record<string, string> = {
  NEW: '新发现',
  REVIEWING: '正在评估',
  CONTACTED: '已联系',
  RELATIONSHIP_VERIFIED: '关系已确认',
  PREPARING: '准备中',
  BID_SUBMITTED: '已投标',
  WON: '已成交',
  LOST: '未成交',
  NOT_FIT: '不适合',
  MONITOR: '持续观察',
  ARCHIVED: '已归档',
}

const ACTIVE_STATUSES = new Set([
  'NEW', 'REVIEWING', 'CONTACTED', 'RELATIONSHIP_VERIFIED', 'PREPARING', 'BID_SUBMITTED',
])
const CLOSED_STATUSES = new Set(['WON', 'LOST', 'NOT_FIT', 'ARCHIVED'])

type PipelineFilter = 'ALL' | 'ACTIVE' | 'MONITOR' | 'WON' | 'CLOSED'

function buyerLabel(item: FollowedOpportunity): string {
  return item.facts.hospital_name ?? item.facts.buyer_name ?? '采购单位暂无公开信息'
}

function searchText(item: FollowedOpportunity): string {
  return [
    item.facts.project_number,
    item.facts.project_name,
    item.facts.hospital_name,
    item.facts.buyer_name,
    item.facts.department,
    item.facts.region,
    item.latest_note,
    ...item.facts.product_categories,
    ...item.facts.product_items.flatMap((product) => [product.name, product.category]),
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
}

function matchesFilter(item: FollowedOpportunity, filter: PipelineFilter): boolean {
  if (filter === 'ACTIVE') return ACTIVE_STATUSES.has(item.followup_status)
  if (filter === 'MONITOR') return item.followup_status === 'MONITOR'
  if (filter === 'WON') return item.followup_status === 'WON'
  if (filter === 'CLOSED') return CLOSED_STATUSES.has(item.followup_status)
  return true
}

export function FollowedPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const focusedId = searchParams.get('focus')
  const [items, setItems] = useState<FollowedOpportunity[]>([])
  const [statusIndex, setStatusIndex] = useState<FollowedStatusIndexItem[]>([])
  const [nextOffset, setNextOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<PipelineFilter>('ALL')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [page, index] = await Promise.all([
        getFollowedOpportunityPage(0),
        getFollowedStatusIndex(),
      ])
      let nextItems = page.items
      if (focusedId && !nextItems.some((item) => item.opportunity_id === focusedId)) {
        const focused = await getFollowedOpportunityById(focusedId)
        if (focused) nextItems = [focused, ...nextItems]
      }
      setItems(nextItems)
      setStatusIndex(index)
      setNextOffset(page.offset + 100)
      setHasMore(page.has_more)
    } catch (cause) {
      if (isAuthRequiredError(cause)) {
        navigate('/login', { replace: true })
        return
      }
      setError('我的跟进加载失败，请稍后重试。')
    } finally {
      setLoading(false)
    }
  }, [focusedId, navigate])

  const loadMore = useCallback(async () => {
    if (!hasMore || loadingMore) return
    setLoadingMore(true)
    try {
      const page = await getFollowedOpportunityPage(nextOffset)
      setItems((current) => {
        const seen = new Set(current.map((item) => item.opportunity_id))
        return [...current, ...page.items.filter((item) => !seen.has(item.opportunity_id))]
      })
      setNextOffset(page.offset + 100)
      setHasMore(page.has_more)
    } catch (cause) {
      if (isAuthRequiredError(cause)) {
        navigate('/login', { replace: true })
        return
      }
      setError('更早的跟进记录加载失败，请稍后重试。')
    } finally {
      setLoadingMore(false)
    }
  }, [hasMore, loadingMore, navigate, nextOffset])

  useEffect(() => {
    void load()
  }, [load])

  const metrics = useMemo(() => ({
    total: statusIndex.length,
    active: statusIndex.filter((item) => ACTIVE_STATUSES.has(item.followup_status)).length,
    reminders: statusIndex.filter((item) => Boolean(item.remind_at)).length,
    won: statusIndex.filter((item) => item.followup_status === 'WON').length,
  }), [statusIndex])

  const filteredItems = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return items.filter((item) =>
      matchesFilter(item, filter) && (!needle || searchText(item).includes(needle)),
    )
  }, [filter, items, query])

  const orderedItems = useMemo(() => {
    if (!focusedId) return filteredItems
    const focused = filteredItems.find((item) => item.opportunity_id === focusedId)
    if (!focused) return filteredItems
    return [focused, ...filteredItems.filter((item) => item.opportunity_id !== focusedId)]
  }, [filteredItems, focusedId])

  if (loading) return <LoadingState />
  if (error) return <ErrorState message={error} onRetry={() => void load()} />
  if (items.length === 0) {
    return (
      <EmptyState
        title="暂无跟进中的商机"
        hint="在今日行动或商机池中加入跟进、标记已联系或设置提醒后，会进入这里。"
      />
    )
  }

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">我的跟进</h2>
            <p className="mt-1 max-w-3xl text-[13px] leading-6 text-slate-500">
              把正在推进、观察、已投标和已结束的项目放在同一条销售时间线上。即使商机退出当前公开机会池，私有跟进记录仍会保留并可继续更新。
            </p>
          </div>
          <button
            type="button"
            onClick={() => void load()}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-[12px] text-slate-600 hover:bg-slate-50"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            刷新
          </button>
        </div>
      </section>

      <section className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[
          ['全部跟进', metrics.total],
          ['正在推进', metrics.active],
          ['已设提醒', metrics.reminders],
          ['已成交', metrics.won],
        ].map(([label, value]) => (
          <div key={String(label)} className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
            <p className="text-[11px] text-slate-500">{label}</p>
            <p className="mt-1 text-xl font-semibold text-slate-900">{value}</p>
          </div>
        ))}
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
        <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
          <label className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索已加载的医院、项目、产品、备注..."
              className="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 pl-9 pr-3 text-[13px] outline-none focus:border-teal-500 focus:bg-white"
            />
          </label>
          <div className="flex min-w-0 items-center gap-1 overflow-x-auto rounded-xl border border-slate-200 bg-slate-50 p-1">
            <Filter className="ml-2 h-3.5 w-3.5 shrink-0 text-slate-400" />
            {([
              ['ALL', '全部'],
              ['ACTIVE', '推进中'],
              ['MONITOR', '观察'],
              ['WON', '成交'],
              ['CLOSED', '已结束'],
            ] as const).map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => setFilter(value)}
                className={`shrink-0 rounded-lg px-2.5 py-1.5 text-[12px] font-medium ${
                  filter === value ? 'bg-white text-teal-800 shadow-sm' : 'text-slate-500'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <p className="mt-2 px-1 text-[11px] text-slate-400">当前显示 {orderedItems.length} 条 · 已加载详情 {items.length} / 全部 {statusIndex.length} 条{hasMore ? ' · 搜索仅覆盖已加载详情，可继续加载更早记录' : ''}</p>
      </section>

      {orderedItems.length === 0 ? (
        <EmptyState title="没有符合条件的跟进项目" hint="可以清空搜索词或切换状态筛选。" />
      ) : (
        <div className="space-y-3">
          {orderedItems.map((item) => {
            const focused = item.opportunity_id === focusedId
            const keyDate = item.facts.bid_deadline ?? item.facts.expected_procurement_at
            return (
              <article
                key={item.opportunity_id}
                className={
                  focused
                    ? 'rounded-2xl border border-amber-300 bg-amber-50/40 p-4 shadow-sm'
                    : 'rounded-2xl border border-slate-200 bg-white p-4 shadow-sm'
                }
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded-md bg-teal-50 px-2 py-0.5 text-[11px] font-medium text-teal-800 ring-1 ring-teal-200">
                        {STATUS_LABELS[item.followup_status] ?? item.followup_status}
                      </span>
                      {focused ? (
                        <span className="text-[11px] font-medium text-amber-800">来自到期提醒</span>
                      ) : null}
                      {item.remind_at ? (
                        <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] text-amber-800 ring-1 ring-amber-100">已设提醒</span>
                      ) : null}
                    </div>
                    <h3 className="mt-2 text-[14px] font-semibold leading-6 text-slate-900">
                      {buyerLabel(item)}
                    </h3>
                    <p className="mt-0.5 text-[13px] leading-5 text-slate-700">
                      {item.facts.project_name ?? '项目名称暂无公开信息'}
                    </p>
                    {item.facts.product_categories.length ? (
                      <p className="mt-1 line-clamp-2 text-[11px] leading-5 text-slate-400">
                        {item.facts.product_categories.slice(0, 4).join('、')}
                      </p>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    onClick={() => navigate(`/opportunity/${encodeURIComponent(item.opportunity_id)}`)}
                    className="inline-flex min-h-9 shrink-0 items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[12px] font-medium text-slate-700 hover:bg-slate-50"
                  >
                    查看详情
                    <ChevronRight className="h-3.5 w-3.5" />
                  </button>
                </div>

                <div className="mt-3 grid gap-2 text-[12px] text-slate-600 sm:grid-cols-2 lg:grid-cols-4">
                  <div>
                    <span className="text-slate-400">项目阶段：</span>
                    {item.facts.lifecycle_state ?? '暂无公开信息'}
                  </div>
                  <div>
                    <span className="text-slate-400">公开预算：</span>
                    {formatBudget(item.facts.budget_cny) ?? '暂无公开信息'}
                  </div>
                  <div>
                    <span className="text-slate-400">关键日期：</span>
                    {formatDate(keyDate) ?? '暂无公开信息'}
                  </div>
                  <div>
                    <span className="text-slate-400">最近跟进：</span>
                    {formatDateTime(item.followup_updated_at) ?? item.followup_updated_at}
                  </div>
                </div>

                {item.remind_at || item.latest_note ? (
                  <div className="mt-3 rounded-xl bg-slate-50 px-3 py-2 text-[12px] leading-5 text-slate-600">
                    {item.remind_at ? (
                      <p>提醒时间：{formatDateTime(item.remind_at) ?? item.remind_at}</p>
                    ) : null}
                    {item.latest_note ? <p className="whitespace-pre-wrap">最近备注：{item.latest_note}</p> : null}
                  </div>
                ) : null}

                <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                  <p className="text-[11px] text-slate-400">
                    公开快照与当前账号私有跟进分开保存；历史项目仍可维护结果和备注。
                  </p>
                  {item.evidence_source_urls.length ? (
                    <div className="flex flex-wrap gap-2">
                      {item.evidence_source_urls.slice(0, 2).map((url, index) => (
                        <a
                          key={url}
                          href={url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-[12px] text-slate-600"
                        >
                          官方依据{item.evidence_source_urls.length > 1 ? ` ${index + 1}` : ''}
                          <ExternalLink className="h-3.5 w-3.5" />
                        </a>
                      ))}
                    </div>
                  ) : null}
                </div>
              </article>
            )
          })}
        </div>
      )}

      {hasMore ? (
        <div className="flex justify-center">
          <button
            type="button"
            disabled={loadingMore}
            onClick={() => void loadMore()}
            className="min-h-10 rounded-xl border border-slate-200 bg-white px-4 text-[12px] font-medium text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-50"
          >
            {loadingMore ? '正在加载…' : '加载更早跟进'}
          </button>
        </div>
      ) : null}
    </div>
  )
}
