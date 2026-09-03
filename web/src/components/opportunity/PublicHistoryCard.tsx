import { History, RefreshCw } from 'lucide-react'
import type {
  PublicHistoryChange,
  PublicOpportunityHistory,
} from '@/services/publicOpportunityHistoryApi'
import { formatDateTime } from '@/utils/format'

const FIELD_LABELS: Record<string, string> = {
  'facts.project_number': '项目编号',
  'facts.project_name': '项目名称',
  'facts.buyer_name': '采购单位',
  'facts.hospital_name': '医院',
  'facts.department': '科室',
  'facts.lifecycle_state': '项目阶段',
  'facts.notice_type': '公告类型',
  'facts.published_at': '发布时间',
  'facts.registration_deadline': '报名/文件获取截止',
  'facts.registration_deadline_date': '报名截止日期',
  'facts.bid_deadline': '投标/响应截止',
  'facts.expected_procurement_at': '预计采购时间',
  'facts.budget': '公开预算',
  'facts.procurement_method': '采购方式',
  'facts.product_categories': '产品分类',
  'facts.product_items': '产品/设备明细',
  'facts.public_contact': '公开联系人',
  'facts.quality_flags': '事实质量标记',
  'evidence_source_urls': '官方依据',
}

function textValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '未提供'
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return '空'
    const simple = value.every((item) => ['string', 'number', 'boolean'].includes(typeof item))
    return simple ? value.join('、') : `共 ${value.length} 项内容`
  }
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>
    const amount = record.amount_cny ?? record.amount ?? record.value
    if (typeof amount === 'number') {
      if (amount < 10_000) return `${Math.round(amount)} 元`
      return `${Number((amount / 10_000).toFixed(amount < 100_000 ? 2 : 1))} 万元`
    }
    const contactBits = [record.name, record.title, record.phone, record.email]
      .filter((item): item is string => typeof item === 'string' && Boolean(item.trim()))
    if (contactBits.length) return contactBits.join(' · ')
    return '结构化内容已更新'
  }
  return '内容已更新'
}

function ChangeRow({ change }: { change: PublicHistoryChange }) {
  const label = FIELD_LABELS[change.field] ?? change.field.replace(/^facts\./, '')
  return (
    <div className="rounded-lg bg-slate-50 px-2.5 py-2">
      <p className="text-[12px] font-medium text-slate-700">{label}</p>
      <div className="mt-1 grid gap-1 text-[11px] leading-5 text-slate-500 sm:grid-cols-2">
        <p className="min-w-0 break-words"><span className="text-slate-400">原：</span>{textValue(change.before)}</p>
        <p className="min-w-0 break-words"><span className="text-slate-400">新：</span>{textValue(change.after)}</p>
      </div>
    </div>
  )
}

export function PublicHistoryCard({
  history,
  loading,
  error,
}: {
  history: PublicOpportunityHistory | null
  loading: boolean
  error: boolean
}) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <History className="h-4 w-4 text-teal-700" />
          <div>
            <h3 className="text-[14px] font-semibold text-slate-900">公开信息更新记录</h3>
            <p className="mt-0.5 text-[11px] leading-4 text-slate-500">
              只记录已核验官方公开事实的版本变化，不包含你的医院关系或产品资源。
            </p>
          </div>
        </div>
        {history?.current_version ? (
          <span className="shrink-0 rounded-full bg-slate-100 px-2 py-1 text-[11px] text-slate-600">
            当前 v{history.current_version}
          </span>
        ) : null}
      </div>

      {loading ? (
        <div className="mt-3 flex items-center gap-2 text-[12px] text-slate-500">
          <RefreshCw className="h-3.5 w-3.5 animate-spin" />
          正在读取版本记录…
        </div>
      ) : error ? (
        <p className="mt-3 text-[12px] leading-5 text-slate-500">
          更新记录暂时不可用；当前商机事实和官方依据不受影响。
        </p>
      ) : !history || history.versions.length === 0 ? (
        <p className="mt-3 text-[12px] leading-5 text-slate-500">
          当前尚未形成可展示的版本历史。后续同一商机的已核验公开事实发生变化时，会在这里保留记录。
        </p>
      ) : (
        <div className="mt-3 space-y-2.5">
          {history.versions.map((version) => (
            <article key={version.version} className="rounded-xl border border-slate-100 px-3 py-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                    version.change_type === 'INITIAL'
                      ? 'bg-slate-100 text-slate-700'
                      : 'bg-teal-50 text-teal-800'
                  }`}>
                    {version.change_type === 'INITIAL' ? '首次收录' : `更新 v${version.version}`}
                  </span>
                  <span className="text-[11px] text-slate-400">
                    {formatDateTime(version.observed_at) ?? version.observed_at}
                  </span>
                </div>
                {version.change_type === 'UPDATED' ? (
                  <span className="text-[11px] text-slate-400">
                    {version.changes.length} 个公开字段变化
                  </span>
                ) : null}
              </div>
              {version.change_type === 'UPDATED' && version.changes.length ? (
                <div className="mt-2 space-y-1.5">
                  {version.changes.slice(0, 8).map((change) => (
                    <ChangeRow key={`${version.version}-${change.field}`} change={change} />
                  ))}
                  {version.changes.length > 8 ? (
                    <p className="text-[11px] text-slate-400">另有 {version.changes.length - 8} 个字段变化</p>
                  ) : null}
                </div>
              ) : version.change_type === 'UPDATED' ? (
                <p className="mt-2 text-[11px] text-slate-500">本次版本有公开事实变化，详细字段已按安全白名单过滤。</p>
              ) : (
                <p className="mt-2 text-[11px] text-slate-500">这是系统首次保存该商机的已核验公开事实版本。</p>
              )}
            </article>
          ))}
          {history.has_more ? (
            <p className="text-[11px] text-slate-400">当前展示最近 20 个版本，更早历史仍保存在公共版本库中。</p>
          ) : null}
        </div>
      )}
    </section>
  )
}
