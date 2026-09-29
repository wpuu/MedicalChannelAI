import { AlertTriangle, ExternalLink } from 'lucide-react'
import type { OfficialNotice } from '@/types'

function noticeVerb(notice: OfficialNotice): string {
  return notice.event_type === 'TERMINATION' ? '已终止 / 废标' : '有更正公告'
}

export function officialNoticeHeadline(notices: readonly OfficialNotice[]): string {
  const terminated = notices.filter((notice) => notice.event_type === 'TERMINATION').flatMap((notice) => notice.packages)
  const corrected = notices.filter((notice) => notice.event_type === 'CORRECTION').flatMap((notice) => notice.packages)
  const parts: string[] = []
  if (terminated.length) parts.push(`${Array.from(new Set(terminated)).join('、')} 已终止 / 废标`)
  if (corrected.length) parts.push(`${Array.from(new Set(corrected)).join('、')} 有更正公告`)
  return parts.join('；')
}

/** One-line amber pill for list cards: which packages an official notice concerns. */
export function OfficialNoticeInline({ notices }: { notices: readonly OfficialNotice[] }) {
  if (!notices.length) return null
  return (
    <div className="inline-flex max-w-full items-start gap-1.5 rounded-lg border border-amber-200 bg-amber-50/80 px-2.5 py-1.5 text-[12px] leading-5 text-amber-950">
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" />
      <span>
        官方公告：{officialNoticeHeadline(notices)}，其余包不受影响，详见详情页。
      </span>
    </div>
  )
}

/**
 * Detail-page block for package-scoped 更正/终止/废标 notices. The opportunity
 * stays open for the other packages; the seller must read the notice itself.
 */
export function OfficialNoticeBanner({ notices }: { notices: readonly OfficialNotice[] }) {
  if (!notices.length) return null
  return (
    <section
      className="rounded-2xl border border-amber-200 bg-amber-50/70 px-4 py-4 text-amber-950"
      aria-labelledby="official-notice-heading"
    >
      <h3 id="official-notice-heading" className="flex items-center gap-2 text-[14px] font-semibold">
        <AlertTriangle className="h-4 w-4 text-amber-600" />
        官方公告涉及本项目的部分包
      </h3>
      <p className="mt-1 text-[12px] leading-5 text-amber-900/80">
        以下公告只针对点名的包；其余包仍按原公告进行。本页事实未因这些公告改写，请以官方公告原文为准。
      </p>
      <ul className="mt-2 space-y-2">
        {notices.map((notice) => (
          <li key={`${notice.source_url}:${notice.packages.join(',')}`} className="rounded-xl border border-amber-200/80 bg-white/70 px-3 py-2 text-[13px] leading-5">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
              <span className="font-medium">
                {notice.packages.join('、')} {noticeVerb(notice)}
              </span>
              <span className="text-[12px] text-amber-900/70">公告 {notice.published_at}</span>
            </div>
            {notice.summary ? <p className="mt-1 text-[12px] leading-5 text-amber-900/90">{notice.summary}</p> : null}
            <a
              href={notice.source_url}
              target="_blank"
              rel="noreferrer"
              className="mt-1 inline-flex items-center gap-1 text-[12px] text-sky-700 underline-offset-2 hover:underline"
            >
              查看官方公告
              <ExternalLink className="h-3 w-3" />
            </a>
          </li>
        ))}
      </ul>
    </section>
  )
}
