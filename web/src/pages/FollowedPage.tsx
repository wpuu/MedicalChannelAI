import { useCallback, useEffect, useMemo, useState } from 'react'
import { ChevronRight, ExternalLink, Filter, RefreshCw, Search } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { OutcomeSummaryCard } from '@/components/followup/OutcomeSummaryCard'
import { AwardResultNotice } from '@/components/shared/AwardResultNotice'
import { EmptyState, ErrorState, LoadingState } from '@/components/shared/PageStates'
import { isAuthRequiredError } from '@/services/apiConfig'
import { findAwardForProject, getAwardLedger } from '@/services/verifiedOpportunityPool'
import type { AwardLedgerEntry } from '@/types'
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
const NEXT_ACTION_PREFIX = '下次行动：'
const LOST_REASON_PREFIX = '未成交原因（当前用户判断）：'
const GENERIC_REMINDER_NOTE = '设置下次跟进提醒；销售阶段保持不变。'

type PipelineFilter = 'ALL' | 'DUE' | 'ACTIVE' | 'MONITOR' | 'WON' | 'CLOSED'

interface NotePresentation {
  label: string
  text: string
}

function buyerLabel(item: FollowedOpportunity): string {
  return item.facts.hospital_name ?? item.facts.buyer_name ?? '采购单位暂无公开信息'
}

function reminderIsDue(item: Pick<FollowedOpportunity, 'followup_status' | 'remind_at'>): boolean {
  if (!item.remind_at || CLOSED_STATUSES.has(item.followup_status)) return false
  const timestamp = Date.parse(item.remind_at)
  return !Number.isNaN(timestamp) && timestamp <= Date.now()
}

function needsNextAction(item: Pick<FollowedOpportunity, 'followup_status' | 'remind_at'>): boolean {
  return ACTIVE_STATUSES.has(item.followup_status) && !item.remind_at
}

function notePresentation(item: FollowedOpportunity): NotePresentation | null {
  const note = item.latest_note?.trim()
  if (!note || note === GENERIC_REMINDER_NOTE) return null
  if (note.startsWith(NEXT_ACTION_PREFIX)) {
    const text = note.slice(NEXT_ACTION_PREFIX.length).trim()
    return text ? { label: '下一步', text } : null
  }
  if (item.followup_status === 'LOST' && note.startsWith(LOST_REASON_PREFIX)) {
    const text = note.slice(LOST_REASON_PREFIX.length).trim()
    return text ? { label: '未成交复盘（私有）', text } : null
  }
  return { label: '最近备注', text: note }
}

function actionTier(item: FollowedOpportunity): number {
  if (reminderIsDue(item)) return 0
  if (!CLOSED_STATUSES.has(item.followup_status) && item.remind_at) return 1
  if (ACTIVE_STATUSES.has(item.followup_status)) return 2
  if (item.followup_status === 'MONITOR') return 3
  return 4
}

function compareForActionView(left: FollowedOpportunity, right: FollowedOpportunity): number {
  const tierDiff = actionTier(left) - actionTier(right)
  if (tierDiff !== 0) return tierDiff

  if (actionTier(left) <= 1) {
    const leftReminder = left.remind_at ? Date.parse(left.remind_at) : Number.POSITIVE_INFINITY
    const rightReminder = right.remind_at ? Date.parse(right.remind_at) : Number.POSITIVE_INFINITY
    if (leftReminder !== rightReminder) return leftReminder - rightReminder
  }

  return Date.parse(right.followup_updated_at) - Date.parse(left.followup_updated_at)
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
  if (filter === 'DUE') return reminderIsDue(item)
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
  const [awardLedger, setAwardLedger] = useState<AwardLedgerEntry[]>([])
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
    let cancelled = false
    // Best effort, public data: lets a followed project that has since been
    // awarded show its result instead of looking silently stale.
    void getAwardLedger()
      .then((ledger) => {
        if (!cancelled) setAwardLedger(ledger.entries)
      })
      .catch(() => {
        if (!cancelled) setAwardLedger([])
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const metrics = useMemo(() => ({
    total: statusIndex.length,
    active: statusIndex.filter((item) => ACTIVE_STATUSES.has(item.followup_status)).length,
    due: statusIndex.filter((item) => reminderIsDue(item)).length,
    won: statusIndex.filter((item) => item.followup_status === 'WON').length,
  }), [statusIndex])

  const filteredItems = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return items.filter((item) =>
      matchesFilter(item, filter) && (!needle || searchText(item).includes(needle)),
    )
  }, [filter, items, query])

  const orderedItems = useMemo(() => {
    const actionOrdered = [...filteredItems].sort(compareForActionView)
    if (!focusedId) return actionOrdered
    const focused = actionOrdered.find((item) => item.opportunity_id === focusedId)
    if (!focused) return actionOrdered
    return [focused, ...actionOrdered.filter((item) => item.opportunity_id !== focusedId)]
  }, [filteredItems, focusedId])

  if (loading) return <LoadingState />
  if (error) return <ErrorState message={error} onRetry={() => void load()} />
  if (items.length === 0) {
    return (
      <EmptyState
        title="暂无跟进中的商机"
        hint="在今日行动或商机池中加入跟进、标记已联系或安排下一步后，会进入这里。"
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
              已到期和近期安排的下一步优先显示，再看其他推进、观察和已结束项目。标记“待安排下一步”的推进项目还没有私有提醒时间，需要你明确决定后续动作；系统不会自动替你生成。即使商机退出当前公开机会池，私有跟进记录仍会保留并可继续更新。
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
          ['待处理', metrics.due],
          ['已成交', metrics.won],
        ].map(([label, value]) => (
          <div key={String(label)} className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
            <p className="text-[11px] text-slate-500">{label}</p>
            <p className="mt-1 text-xl font-semibold text-slate-900">{value}</p>
          </div>
        ))}
      </section>

      <OutcomeSummaryCard />

      <section className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
        <div className="flex flex-col gap-2 lg:flex-row lg:items-center">
          <label className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索已加载的医院、项目、产品、下一步、备注..."
              className="h-10 w-full rounded-xl border border-slate-200 bg-slate-50 pl-9 pr-3 text-[13px] outline-none focus:border-teal-500 focus:bg-white"
            />
          </label>
          <div className="flex min-w-0 items-center gap-1 overflow-x-auto rounded-xl border border-slate-200 bg-slate-50 p-1">
            <Filter className="ml-2 h-3.5 w-3.5 shrink-0 text-slate-400" />
            {([
              ['ALL', '全部'],
              ['DUE', '待处理'],
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
        <p className="mt-2 px-1 text-[11px] text-slate-400">当前显示 {orderedItems.length} 条 · 已加载详情 {items.length} / 全部 {statusIndex.length} 条{hasMore ? ' · 搜索与行动排序仅覆盖已加载详情，可继续加载更早记录' : ''}</p>
      </section>

      {orderedItems.length === 0 ? (
        <EmptyState title="没有符合条件的跟进项目" hint="可以清空搜索词或切换状态筛选。" />
      ) : (
        <div className="space-y-3">
          {orderedItems.map((item) => {
            const focused = item.opportunity_id === focusedId
            const keyDate = item.facts.bid_deadline ?? item.facts.expected_procurement_at
            const privateNote = notePresentation(item)
            const due = reminderIsDue(item)
            const pendingNextAction = needsNextAction(item)
            const awardResult = findAwardForProject(awardLedger, item.facts.project_number, item.facts.market_code)
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
                      {due ? (
                        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-900 ring-1 ring-amber-200">已到期</span>
                      ) : item.remind_at ? (
                        <span className="rounded-full bg-slate-50 px-2 py-0.5 text-[11px] text-slate-600 ring-1 ring-slate-200">已安排</span>
                      ) : pendingNextAction ? (
                        <span className="rounded-full bg-rose-50 px-2 py-0.5 text-[11px] font-medium text-rose-700 ring-1 ring-rose-200">待安排下一步</span>
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
                    {awardResult ? <AwardResultNotice entry={awardResult} compact /> : null}
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

                {item.remind_at || privateNote ? (
                  <div className={due ? 'mt-3 rounded-xl bg-amber-50 px-3 py-2 text-[12px] leading-5 text-amber-900' : 'mt-3 rounded-xl bg-slate-50 px-3 py-2 text-[12px] leading-5 text-slate-600'}>
                    {item.remind_at ? (
                      <p><span className="font-medium">{due ? '到期时间' : '下次时间'}：</span>{formatDateTime(item.remind_at) ?? item.remind_at}</p>
                    ) : null}
                    {privateNote ? (
                      <p className="whitespace-pre-wrap"><span className="font-medium">{privateNote.label}：</span>{privateNote.text}</p>
                    ) : null}
                  </div>
                ) : null}

                <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                  <p className="text-[11px] text-slate-400">
                    公开快照与当前账号私有跟进分开保存；下一步、结果与复盘均属于私有跟进数据。
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