import { useCallback, useEffect, useMemo, useState } from 'react'
import { ExternalLink, RefreshCw } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { EmptyState, ErrorState, LoadingState } from '@/components/shared/PageStates'
import { isAuthRequiredError } from '@/services/apiConfig'
import {
  getFollowedOpportunities,
  type FollowedOpportunity,
} from '@/services/followedApi'
import { formatBudget, formatDate, formatDateTime } from '@/utils/format'

const STATUS_LABELS: Record<string, string> = {
  NEW: '新建',
  REVIEWING: '继续跟进',
  CONTACTED: '已联系',
  RELATIONSHIP_VERIFIED: '关系已确认',
  PREPARING: '准备中',
  BID_SUBMITTED: '已投标',
  WON: '已赢单',
  LOST: '已失单',
  NOT_FIT: '不适合',
  MONITOR: '持续观察',
}

function buyerLabel(item: FollowedOpportunity): string {
  return item.facts.hospital_name ?? item.facts.buyer_name ?? '采购单位暂无公开信息'
}

export function FollowedPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const focusedId = searchParams.get('focus')
  const [items, setItems] = useState<FollowedOpportunity[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setItems(await getFollowedOpportunities())
    } catch (cause) {
      if (isAuthRequiredError(cause)) {
        navigate('/login', { replace: true })
        return
      }
      setError('我的跟进加载失败，请稍后重试。')
    } finally {
      setLoading(false)
    }
  }, [navigate])

  useEffect(() => {
    void load()
  }, [load])

  const orderedItems = useMemo(() => {
    if (!focusedId) return items
    const focused = items.find((item) => item.opportunity_id === focusedId)
    if (!focused) return items
    return [focused, ...items.filter((item) => item.opportunity_id !== focusedId)]
  }, [focusedId, items])

  if (loading) return <LoadingState />
  if (error) return <ErrorState message={error} onRetry={() => void load()} />
  if (items.length === 0) {
    return (
      <EmptyState
        title="暂无跟进中的商机"
        hint="在今日行动中点击已联系、继续跟进或稍后提醒后，会进入这里。"
      />
    )
  }

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">我的跟进</h2>
            <p className="mt-1 text-[13px] leading-6 text-slate-500">
              这里保留已进入跟进流程的商机，即使它已经不在今天的 Top5。公开事实与客户跟进状态仍分开保存。
            </p>
          </div>
          <button
            type="button"
            onClick={() => void load()}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-[12px] text-slate-600"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            刷新
          </button>
        </div>
      </section>

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
                  </div>
                  <h3 className="mt-2 text-[14px] font-semibold leading-6 text-slate-900">
                    {buyerLabel(item)}
                  </h3>
                  <p className="mt-0.5 text-[13px] leading-5 text-slate-700">
                    {item.facts.project_name ?? '项目名称暂无公开信息'}
                  </p>
                </div>
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
                  {item.latest_note ? <p>最近备注：{item.latest_note}</p> : null}
                </div>
              ) : null}

              <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                <p className="text-[11px] text-slate-400">
                  官方事实来自公开采购数据；跟进状态属于当前客户私有信息。
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
    </div>
  )
}
