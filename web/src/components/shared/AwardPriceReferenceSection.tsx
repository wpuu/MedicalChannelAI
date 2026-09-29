import { useMemo, useState } from 'react'
import { ExternalLink, Tags } from 'lucide-react'
import type { AwardPriceReference, AwardPriceReferenceRow } from '@/types'
import { ENABLED_MARKETS } from '@/config/marketPreference'
import { deviceFamilyLabel, normalizeDeviceName } from '@/utils/deviceFamily'
import { formatBudget } from '@/utils/format'

const DEFAULT_VISIBLE_ROWS = 8

interface AwardPriceReferenceSectionProps {
  reference: AwardPriceReference | null
  /** Only rows of these market codes are shown (user's 业务地区 preference). */
  marketCodes?: ReadonlySet<string>
}

function marketName(code: string | null | undefined): string | null {
  if (!code) return null
  return ENABLED_MARKETS.find((market) => market.code === code)?.name ?? null
}

export function priceText(value: number): string {
  return formatBudget(value) ?? `¥${value.toLocaleString('zh-CN')}`
}

/**
 * Case/width-insensitive keyword filter over name, brand, model, buyer and the
 * family label, so "彩超" also finds rows named 彩色多普勒超声诊断仪.
 */
export function filterReferenceRows(
  rows: readonly AwardPriceReferenceRow[],
  keyword: string,
  families?: AwardPriceReference['families'] | null,
): AwardPriceReferenceRow[] {
  const needle = normalizeDeviceName(keyword)
  if (!needle) return [...rows]
  return rows.filter((row) =>
    [row.name, row.brand, row.model, row.buyer_name, deviceFamilyLabel(row.family, families)].some(
      (field) => field && normalizeDeviceName(field).includes(needle),
    ),
  )
}

export function ReferenceRowLine({ row, families }: { row: AwardPriceReferenceRow; families: AwardPriceReference['families'] }) {
  const market = marketName(row.market_code)
  const familyLabel = deviceFamilyLabel(row.family, families)
  return (
    <li className="flex flex-col gap-1 py-2.5 text-[13px] leading-5 text-slate-700">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className="font-medium text-slate-900">{row.name}</span>
        <span className="font-semibold text-slate-900">
          {priceText(row.unit_price_cny)}
          <span className="ml-1 text-[11px] font-normal text-slate-500">/ 单价</span>
        </span>
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-[12px] text-slate-600">
        <span>
          {row.brand}
          {row.model ? ` · ${row.model}` : ''}
        </span>
        {row.quantity ? <span>数量 {row.quantity}</span> : null}
        {row.line_count > 1 ? <span>同款 {row.line_count} 行</span> : null}
        {familyLabel ? <span className="text-slate-400">{familyLabel}</span> : null}
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-slate-500">
        {market ? <span className="rounded-full border border-sky-200 bg-sky-50 px-1.5 text-[11px] text-sky-700">{market}</span> : null}
        <span>{row.buyer_name ?? '采购人未公布'}</span>
        {row.published_at ? <span>公告 {row.published_at}</span> : null}
        <a
          href={row.source_url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 text-sky-700 underline-offset-2 hover:underline"
        >
          官方公告
          <ExternalLink className="h-3 w-3" />
        </a>
      </div>
    </li>
  )
}

/**
 * "成交价参考" for the opportunity pool page: every 标的 line of an official
 * 中标/成交 notice that names one brand and one unit price, grouped by coarse
 * device family. Facts only — no averages, no "market price", no advice.
 */
export function AwardPriceReferenceSection({ reference, marketCodes }: AwardPriceReferenceSectionProps) {
  const [family, setFamily] = useState<string | null>(null)
  const [keyword, setKeyword] = useState('')
  const [expanded, setExpanded] = useState(false)

  const scoped = useMemo(
    () => (reference?.rows ?? []).filter((row) => !marketCodes || marketCodes.has(row.market_code)),
    [reference, marketCodes],
  )
  const familyCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const row of scoped) {
      const code = row.family ?? 'OTHER'
      counts.set(code, (counts.get(code) ?? 0) + 1)
    }
    return counts
  }, [scoped])
  const rows = useMemo(() => {
    const byFamily = family ? scoped.filter((row) => (row.family ?? 'OTHER') === family) : scoped
    return filterReferenceRows(byFamily, keyword, reference?.families)
  }, [scoped, family, keyword, reference])

  if (!reference || !scoped.length) return null
  const families = reference.families
  const chips = [
    ...families.filter((item) => familyCounts.has(item.code)).map((item) => ({ code: item.code, label: item.label })),
    ...(familyCounts.has('OTHER') ? [{ code: 'OTHER', label: '其他' }] : []),
  ]
  const visible = expanded ? rows : rows.slice(0, DEFAULT_VISIBLE_ROWS)

  return (
    <section className="mt-8" aria-labelledby="award-price-reference-heading">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 id="award-price-reference-heading" className="flex items-center gap-2 text-[15px] font-semibold text-slate-900">
            <Tags className="h-4 w-4 text-slate-500" />
            成交价参考
          </h2>
          <p className="mt-1 text-[12px] leading-5 text-slate-500">
            来自官方结果公告的品牌 / 型号 / 单价原文，近 {reference.lookback_days} 天内，按设备类别归组。只列公告写明单一品牌与单价的标的行，不做均价或推断。
          </p>
        </div>
        <span className="text-[12px] text-slate-500">{rows.length} 行</span>
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        <button
          type="button"
          onClick={() => setFamily(null)}
          className={`min-h-8 rounded-full border px-2.5 text-[12px] ${family === null ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'}`}
        >
          全部 {scoped.length}
        </button>
        {chips.map((chip) => (
          <button
            key={chip.code}
            type="button"
            onClick={() => setFamily((value) => (value === chip.code ? null : chip.code))}
            className={`min-h-8 rounded-full border px-2.5 text-[12px] ${family === chip.code ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'}`}
          >
            {chip.label} {familyCounts.get(chip.code) ?? 0}
          </button>
        ))}
      </div>

      <label className="mt-3 block">
        <span className="sr-only">按设备、品牌、型号或采购人筛选</span>
        <input
          type="search"
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
          placeholder="搜设备 / 品牌 / 型号 / 采购人，如 彩超、迈瑞、监护仪"
          className="min-h-10 w-full rounded-xl border border-slate-200 bg-white px-3 text-[13px] text-slate-800 placeholder:text-slate-400 focus:border-slate-400 focus:outline-none"
        />
      </label>

      {rows.length ? (
        <ul className="mt-2 divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white px-4 shadow-sm">
          {visible.map((row) => (
            <ReferenceRowLine key={`${row.award_id}:${row.name}:${row.brand}:${row.model ?? ''}:${row.unit_price_cny}`} row={row} families={families} />
          ))}
        </ul>
      ) : (
        <p className="mt-2 rounded-2xl border border-dashed border-slate-200 px-4 py-6 text-center text-[13px] text-slate-500">
          当前筛选下没有成交价记录。
        </p>
      )}
      {rows.length > DEFAULT_VISIBLE_ROWS ? (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="mt-3 inline-flex min-h-9 items-center rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[12px] font-medium text-slate-700 hover:bg-slate-50"
        >
          {expanded ? '收起' : `展开全部 ${rows.length} 行`}
        </button>
      ) : null}
      {reference.truncated ? (
        <p className="mt-2 text-[11px] text-slate-400">仅保留最新 {reference.max_rows} 行；更早的记录请查官方公告。</p>
      ) : null}
    </section>
  )
}
