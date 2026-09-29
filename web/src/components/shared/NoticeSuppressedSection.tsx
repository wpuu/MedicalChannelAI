import { useMemo, useState } from 'react'
import { EyeOff, ExternalLink } from 'lucide-react'
import type { NoticeSuppressedProject } from '@/types'
import { ENABLED_MARKETS } from '@/config/marketPreference'

const DEFAULT_VISIBLE = 5

interface NoticeSuppressedSectionProps {
  projects: readonly NoticeSuppressedProject[]
  /** Exact total across all markets (the list itself is bounded upstream). */
  totalCount: number
  marketCodes?: ReadonlySet<string>
}

function marketName(code: string | null | undefined): string | null {
  if (!code) return null
  return ENABLED_MARKETS.find((market) => market.code === code)?.name ?? null
}

export function suppressionReasonText(project: NoticeSuppressedProject): string {
  if (project.reason === 'TERMINATED') return '官方终止 / 废标公告'
  return '官方更正公告待核对（内容或截止时间可能已变）'
}

/**
 * "为什么这个项目不见了" — opportunities hidden by a project-scoped official
 * 更正/终止 notice. Fail-closed publishing hides them from the pool; this
 * list keeps the decision explainable and links to the notice.
 */
export function NoticeSuppressedSection({ projects, totalCount, marketCodes }: NoticeSuppressedSectionProps) {
  const [expanded, setExpanded] = useState(false)
  const scoped = useMemo(
    () => projects.filter((project) => !marketCodes || !project.market_code || marketCodes.has(project.market_code)),
    [projects, marketCodes],
  )
  if (!scoped.length) return null
  const visible = expanded ? scoped : scoped.slice(0, DEFAULT_VISIBLE)
  const hiddenElsewhere = Math.max(0, totalCount - projects.length)
  return (
    <section className="mt-8" aria-labelledby="notice-suppressed-heading">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 id="notice-suppressed-heading" className="flex items-center gap-2 text-[15px] font-semibold text-slate-900">
            <EyeOff className="h-4 w-4 text-slate-500" />
            因官方公告暂不展示的项目
          </h2>
          <p className="mt-1 text-[12px] leading-5 text-slate-500">
            这些项目收到了针对整个项目的更正或终止公告。为避免展示过期事实，机会池暂不列出它们；确认公告内容后可自行判断是否继续跟进。
            {hiddenElsewhere > 0 ? ` 另有 ${hiddenElsewhere} 个早于本列表范围。` : ''}
          </p>
        </div>
        <span className="text-[12px] text-slate-500">{scoped.length} 个</span>
      </div>
      <ul className="mt-3 divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white px-4 shadow-sm">
        {visible.map((project) => {
          const market = marketName(project.market_code)
          return (
            <li key={`${project.market_code ?? ''}:${project.project_number ?? project.project_name ?? ''}:${project.source_url ?? ''}`} className="py-2.5 text-[13px] leading-5 text-slate-700">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                <span className="font-medium text-slate-900">{project.project_name ?? project.project_number ?? '未命名项目'}</span>
                <span className="text-[12px] text-slate-500">{suppressionReasonText(project)}</span>
              </div>
              <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-slate-500">
                {market ? <span className="rounded-full border border-sky-200 bg-sky-50 px-1.5 text-[11px] text-sky-700">{market}</span> : null}
                {project.buyer_name ? <span>{project.buyer_name}</span> : null}
                {project.project_number ? <span>编号 {project.project_number}</span> : null}
                {project.published_at ? <span>公告 {project.published_at}</span> : null}
                {project.source_url ? (
                  <a
                    href={project.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-sky-700 underline-offset-2 hover:underline"
                  >
                    官方公告
                    <ExternalLink className="h-3 w-3" />
                  </a>
                ) : null}
              </div>
            </li>
          )
        })}
      </ul>
      {scoped.length > DEFAULT_VISIBLE ? (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="mt-3 inline-flex min-h-9 items-center rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-[12px] font-medium text-slate-700 hover:bg-slate-50"
        >
          {expanded ? '收起' : `展开全部 ${scoped.length} 个`}
        </button>
      ) : null}
    </section>
  )
}
