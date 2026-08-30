import { ExternalLink } from 'lucide-react'
import { OfficialText } from '@/components/shared/EmptyValue'
import { SectionCard } from '@/components/shared/SectionCard'
import { SourceTag, VerifiedBadge } from '@/components/shared/StageBadge'
import { isApiMode } from '@/services/apiConfig'

export function EvidenceCard({
  urls,
  verificationStatus,
}: {
  urls: string[]
  verificationStatus: 'VERIFIED' | 'UNVERIFIED' | 'PARTIAL'
}) {
  return (
    <SectionCard
      title="官方依据"
      subtitle={
        isApiMode
          ? '仅展示官方来源，不把第三方搜索结果当作公告'
          : '演示模式：项目是虚构的，下面只展示正式版的官方依据入口形态，不对应真实公告'
      }
      tone="evidence"
      extra={
        <div className="flex flex-col items-end gap-1">
          <SourceTag tone="evidence">{isApiMode ? '查看官方依据' : '演示依据入口'}</SourceTag>
          <VerifiedBadge status={verificationStatus} />
        </div>
      }
    >
      {urls.length === 0 ? (
        <OfficialText value={null} />
      ) : (
        <ul className="space-y-2">
          {urls.map((url) => (
            <li
              key={url}
              className="flex items-start justify-between gap-3 rounded-xl border border-emerald-100 bg-white px-3 py-2.5"
            >
              <p className="min-w-0 break-all text-[12px] leading-5 text-slate-600">{url}</p>
              {isApiMode ? (
                <a
                  href={url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex shrink-0 items-center gap-1 rounded-lg bg-emerald-700 px-2.5 py-1 text-[12px] text-white"
                >
                  打开官方来源
                  <ExternalLink className="h-3 w-3" />
                </a>
              ) : (
                <span className="inline-flex shrink-0 items-center rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[12px] text-emerald-800">
                  虚构项目 · 不跳转
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  )
}
