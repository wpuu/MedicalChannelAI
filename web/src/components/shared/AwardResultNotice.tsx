import { ExternalLink, Gavel } from 'lucide-react'
import { LegalWindowNotice } from '@/components/shared/LegalWindowNotice'
import type { AwardLedgerEntry } from '@/types'
import { formatBudget } from '@/utils/format'

interface AwardResultNoticeProps {
  entry: AwardLedgerEntry
  /** Compact: one line for list items. Full: packages + challenge window + link. */
  compact?: boolean
}

function shortDate(value: string | null | undefined): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value ?? '')
  return match ? `${Number(match[2])}月${Number(match[3])}日` : null
}

function headline(entry: AwardLedgerEntry): string {
  const kind = entry.result_kind === 'DEAL' ? '成交' : '中标'
  if (entry.award_status === 'ALL_PACKAGES_FAILED') return '该项目结果公告：全部包废标'
  if (entry.award_status === 'PARTIALLY_FAILED') return `该项目已公布${kind}结果（部分包废标）`
  return `该项目已公布${kind}结果`
}

function winnersSummary(entry: AwardLedgerEntry): string {
  const awarded = entry.packages.filter((pkg) => pkg.status === 'AWARDED' && pkg.supplier_name)
  const names = Array.from(new Set(awarded.map((pkg) => pkg.supplier_name as string)))
  if (!names.length) return '供应商见官方公告'
  const shown = names.slice(0, 2).join('、')
  return names.length > 2 ? `${shown} 等 ${names.length} 家` : shown
}

/**
 * Shown on a followed/opened opportunity whose project number now has a
 * published 中标/成交 result. Facts only (winner, amount, statutory 质疑期),
 * plus a reminder that the private followup status is the user's to update.
 */
export function AwardResultNotice({ entry, compact = false }: AwardResultNoticeProps) {
  const total = formatBudget(entry.total_amount_cny)
  const published = shortDate(entry.published_at)
  const windowCard = { legal_windows: entry.legal_windows, recommendation_mode: 'AWARDED' }

  if (compact) {
    return (
      <div className="mt-2 flex flex-wrap items-center gap-2 text-[12px] leading-5">
        <span className="inline-flex items-center gap-1 rounded-full border border-indigo-200 bg-indigo-50 px-2 py-0.5 font-medium text-indigo-900">
          <Gavel className="h-3 w-3" />
          {headline(entry)}
          {published ? ` · ${published}` : ''}
        </span>
        <span className="text-slate-700">
          {winnersSummary(entry)}
          {total ? ` · ${total}` : ''}
        </span>
        <LegalWindowNotice card={windowCard} compact />
      </div>
    )
  }

  return (
    <section className="rounded-2xl border border-indigo-200 bg-indigo-50/60 px-4 py-4 text-[13px] leading-6 text-slate-800 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1 rounded-md bg-indigo-700 px-2 py-0.5 text-[11px] font-semibold text-white">
          <Gavel className="h-3 w-3" />
          {headline(entry)}
        </span>
        {entry.notice_type ? <span className="text-[11px] text-slate-500">{entry.notice_type}</span> : null}
        {published ? <span className="text-[11px] text-slate-500">公告日期 {published}</span> : null}
      </div>
      <ul className="mt-2 space-y-1">
        {entry.packages.map((pkg, index) => (
          <li key={`${entry.award_id}-${pkg.package_no ?? index}`} className="flex flex-wrap items-baseline gap-x-2">
            {entry.packages.length > 1 ? (
              <span className="text-[11px] text-slate-400">{pkg.package_no ? `第${pkg.package_no}包` : '标的'}</span>
            ) : null}
            {pkg.status === 'AWARDED' ? (
              <>
                <span className="font-medium text-slate-900">{pkg.supplier_name ?? '供应商未公布'}</span>
                <span className="tabular-nums text-slate-600">{formatBudget(pkg.amount_cny) ?? '金额未公布'}</span>
              </>
            ) : (
              <span className="text-rose-700">废标{pkg.failure_reason ? `：${pkg.failure_reason}` : ''}</span>
            )}
          </li>
        ))}
        {entry.package_count > entry.packages.length ? (
          <li className="text-[11px] text-slate-400">另有 {entry.package_count - entry.packages.length} 个包，见官方公告</li>
        ) : null}
      </ul>
      {total ? (
        <p className="mt-1 text-[12px] text-slate-600">
          {entry.amount_basis === 'PACKAGE_SUM' ? '各包合计' : '公告总金额'} <strong className="font-medium text-slate-900">{total}</strong>
        </p>
      ) : null}
      <div className="mt-3">
        <LegalWindowNotice card={windowCard} />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <a
          href={entry.source_url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex min-h-9 items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[12px] font-medium text-slate-700 hover:bg-slate-50"
        >
          <ExternalLink className="h-3.5 w-3.5" />
          官方公告原文
        </a>
        <span className="text-[11px] text-slate-500">
          结果以官方公告为准。你的跟进状态不会被自动改动：若你参与了本项目，请自行核对并更新结果。
        </span>
      </div>
    </section>
  )
}
