import { useMemo, useState } from 'react'
import { Tags } from 'lucide-react'
import type { AwardPriceReference, AwardPriceReferenceRow, TodayActionCard } from '@/types'
import { deviceFamiliesForNames, deviceFamilyLabel } from '@/utils/deviceFamily'
import { ReferenceRowLine } from '@/components/shared/AwardPriceReferenceSection'

const MAX_ROWS = 6

/** Names that describe what this opportunity buys: 标的 first, project name as fallback. */
export function opportunityDeviceNames(card: TodayActionCard): string[] {
  const names = (card.facts.products ?? []).map((item) => item.name).filter((name): name is string => Boolean(name))
  if (names.length) return names
  return card.facts.project_name ? [card.facts.project_name] : []
}

/** Reference rows whose device family matches any of the opportunity's 标的 families. */
export function relatedReferenceRows(
  card: TodayActionCard,
  reference: AwardPriceReference | null | undefined,
): { families: string[]; rows: AwardPriceReferenceRow[] } {
  if (!reference?.rows?.length) return { families: [], rows: [] }
  const families = deviceFamiliesForNames(opportunityDeviceNames(card), reference.families)
  if (!families.length) return { families, rows: [] }
  const wanted = new Set(families)
  return { families, rows: reference.rows.filter((row) => row.family && wanted.has(row.family)) }
}

interface AwardPriceReferenceNoticeProps {
  card: TodayActionCard
  reference: AwardPriceReference | null
}

/**
 * Detail-page block: recent official 成交 lines for the same device families
 * as this opportunity's 标的 (all six markets — prices do not stop at a
 * province border). Explicitly a reference, not a quote or a prediction.
 */
export function AwardPriceReferenceNotice({ card, reference }: AwardPriceReferenceNoticeProps) {
  const [expanded, setExpanded] = useState(false)
  const related = useMemo(() => relatedReferenceRows(card, reference), [card, reference])
  if (!reference || !related.rows.length) return null
  const labels = related.families.map((code) => deviceFamilyLabel(code, reference.families) ?? code)
  const visible = expanded ? related.rows : related.rows.slice(0, MAX_ROWS)
  return (
    <section className="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm" aria-labelledby="award-price-reference-notice-heading">
      <h3 id="award-price-reference-notice-heading" className="flex items-center gap-2 text-[14px] font-semibold text-slate-900">
        <Tags className="h-4 w-4 text-slate-500" />
        同类设备近期成交参考
      </h3>
      <p className="mt-1 text-[12px] leading-5 text-slate-500">
        本项目标的属于「{labels.join(' / ')}」。以下是近 {reference.lookback_days} 天官方结果公告里同类别的品牌 / 型号 / 单价原文，供报价与参数对照参考；类别相同不代表配置相同，以各自公告为准。
      </p>
      <ul className="mt-2 divide-y divide-slate-100">
        {visible.map((row) => (
          <ReferenceRowLine key={`${row.award_id}:${row.name}:${row.brand}:${row.model ?? ''}:${row.unit_price_cny}`} row={row} families={reference.families} />
        ))}
      </ul>
      {related.rows.length > MAX_ROWS ? (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="mt-2 inline-flex min-h-9 items-center rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[12px] font-medium text-slate-700 hover:bg-slate-50"
        >
          {expanded ? '收起' : `展开全部 ${related.rows.length} 行`}
        </button>
      ) : null}
    </section>
  )
}
