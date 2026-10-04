import { useMemo, useState } from 'react'
import { ExternalLink, Gavel } from 'lucide-react'
import { LegalWindowNotice } from '@/components/shared/LegalWindowNotice'
import type { AwardLedgerEntry } from '@/types'
import { formatBudget } from '@/utils/format'
import { ENABLED_MARKETS } from '@/config/marketPreference'

const MAX_ITEMS_PER_ENTRY = 6
const DEFAULT_VISIBLE_ENTRIES = 5

interface AwardLedgerSectionProps {
  entries: AwardLedgerEntry[]
  /** Only entries of these market codes are shown; entries without a code are always shown. */
  marketCodes?: ReadonlySet<string>
  /** Pool records retired because of a published result (shown as context). */
  awardedProjectCount?: number
}

function amountText(value: number | null | undefined): string {
  const formatted = formatBudget(value)
  return formatted ?? '金额待核验'
}

function marketName(code?: string | null): string | null {
  if (!code) return null
  return ENABLED_MARKETS.find((market) => market.code === code)?.name ?? null
}

function resultLabel(entry: AwardLedgerEntry): string {
  if (entry.award_status === 'ALL_PACKAGES_FAILED') return '全部包废标'
  if (entry.award_status === 'PARTIALLY_FAILED') return entry.result_kind === 'DEAL' ? '部分成交' : '部分中标'
  return entry.result_kind === 'DEAL' ? '成交' : '中标'
}

function toneFor(entry: AwardLedgerEntry): string {
  if (entry.award_status === 'ALL_PACKAGES_FAILED') return 'border-rose-200 bg-rose-50 text-rose-800'
  if (entry.award_status === 'PARTIALLY_FAILED') return 'border-amber-200 bg-amber-50 text-amber-800'
  return 'border-emerald-200 bg-emerald-50 text-emerald-800'
}

function AwardEntry({ entry }: { entry: AwardLedgerEntry }) {
  const items = entry.items.slice(0, MAX_ITEMS_PER_ENTRY)
  const hiddenItems = Math.max(0, entry.item_count - items.length)
  const hiddenPackages = Math.max(0, entry.package_count - entry.packages.length)
  return (
    <article className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="px-4 py-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${toneFor(entry)}`}>
            {resultLabel(entry)}
          </span>
          {marketName(entry.market_code) ? (
            <span className="rounded-full border border-sky-200 bg-sky-50 px-2 py-0.5 text-[11px] text-sky-700">
              {marketName(entry.market_code)}
            </span>
          ) : null}
          {entry.notice_type ? (
            <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] text-slate-600">
              {entry.notice_type}
            </span>
          ) : null}
          {entry.published_at ? (
            <span className="text-[11px] text-slate-400">公告 {entry.published_at}</span>
          ) : null}
          <LegalWindowNotice card={{ legal_windows: entry.legal_windows, recommendation_mode: 'AWARDED' }} compact />
        </div>
        <h3 className="mt-2 text-[15px] font-semibold leading-6 text-slate-900">{entry.buyer_name ?? '采购人未公布'}</h3>
        <p className="mt-0.5 text-[14px] leading-6 text-slate-700">{entry.project_name ?? entry.project_number}</p>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-slate-500">
          <span>项目编号 {entry.project_number}</span>
          <span>
            {entry.amount_basis === 'PACKAGE_SUM' ? '各包合计' : '总金额'}{' '}
            <strong className="font-medium text-slate-800">{amountText(entry.total_amount_cny)}</strong>
          </span>
          {entry.procurement_method ? <span>{entry.procurement_method}</span> : null}
        </div>

        <ul className="mt-3 space-y-1.5 text-[13px] leading-5 text-slate-700">
          {entry.packages.map((pkg, index) => (
            <li key={`${entry.award_id}-pkg-${pkg.package_no ?? index}`} className="flex flex-wrap items-baseline gap-x-2">
              <span className="text-[11px] text-slate-400">{pkg.package_no ? `第${pkg.package_no}包` : '标的'}</span>
              {pkg.status === 'AWARDED' ? (
                <>
                  <span className="font-medium text-slate-900">{pkg.supplier_name ?? '供应商未公布'}</span>
                  <span className="tabular-nums text-slate-600">{amountText(pkg.amount_cny)}</span>
                </>
              ) : (
                <span className="text-rose-700">废标{pkg.failure_reason ? `：${pkg.failure_reason}` : ''}</span>
              )}
            </li>
          ))}
          {hiddenPackages > 0 ? <li className="text-[11px] text-slate-400">另有 {hiddenPackages} 个包，见官方公告</li> : null}
        </ul>

        {items.length ? (
          <details className="mt-3 rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
            <summary className="cursor-pointer select-none text-[12px] font-medium text-teal-700">
              品牌 / 型号 / 单价（{entry.item_count} 项）
            </summary>
            <ul className="mt-2 space-y-1 text-[12px] leading-5 text-slate-600">
              {items.map((item, index) => (
                <li key={`${entry.award_id}-item-${index}`}>
                  {item.package_no ? <span className="text-slate-400">第{item.package_no}包 · </span> : null}
                  <span className="text-slate-800">{item.name ?? '标的'}</span>
                  {item.brand ? <span> · {item.brand}</span> : null}
                  {item.model ? <span> · {item.model}</span> : null}
                  {item.quantity ? <span> · {item.quantity}</span> : null}
                  {item.unit_price_cny !== null && item.unit_price_cny !== undefined ? (
                    <span className="tabular-nums"> · 单价 {amountText(item.unit_price_cny)}</span>
                  ) : null}
                </li>
              ))}
              {hiddenItems > 0 ? <li className="text-slate-400">另有 {hiddenItems} 项，见官方公告</li> : null}
            </ul>
          </details>
        ) : null}

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <a
            href={entry.source_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex min-h-9 items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[12px] font-medium text-slate-700 hover:bg-slate-50"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            官方公告原文
          </a>
          <span className="text-[11px] text-slate-400">以上均为公告原文事实，未做胜率或推断。</span>
        </div>
      </div>
    </article>
  )
}

/**
 * "最新中标 / 成交结果" for the opportunity pool page. Purely factual: who won,
 * for how much, which brand/model, and how long the statutory 质疑期 still runs.
 * Awarded projects are removed from the pool by the pipeline, so this is the
 * only place they remain visible.
 */
export function AwardLedgerSection({ entries, marketCodes, awardedProjectCount = 0 }: AwardLedgerSectionProps) {
  const [expanded, setExpanded] = useState(false)
  const scoped = useMemo(
    () =>
      entries.filter((entry) => !entry.market_code || !marketCodes || marketCodes.has(entry.market_code)),
    [entries, marketCodes],
  )
  if (!scoped.length) return null
  const visible = expanded ? scoped : scoped.slice(0, DEFAULT_VISIBLE_ENTRIES)
  return (
    <section className="mt-8" aria-labelledby="award-ledger-heading">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 id="award-ledger-heading" className="flex items-center gap-2 text-[15px] font-semibold text-slate-900">
            <Gavel className="h-4 w-4 text-slate-500" />
            最新中标 / 成交结果
          </h2>
          <p className="mt-1 text-[12px] leading-5 text-slate-500">
            来自中国政府采购网的结果公告：供应商、金额、品牌型号与质疑期倒计时。
            {awardedProjectCount > 0 ? ` 已有 ${awardedProjectCount} 个池内项目因公布结果退出机会池。` : ''}
          </p>
        </div>
        <span className="text-[12px] text-slate-500">{scoped.length} 条</span>
      </div>
      <div className="mt-3 space-y-3">
        {visible.map((entry) => (
          <AwardEntry key={entry.award_id} entry={entry} />
        ))}
      </div>
      {scoped.length > DEFAULT_VISIBLE_ENTRIES ? (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="mt-3 inline-flex min-h-9 items-center rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[12px] font-medium text-slate-700 hover:bg-slate-50"
        >
          {expanded ? '收起' : `展开全部 ${scoped.length} 条`}
        </button>
      ) : null}
    </section>
  )
}
