import type { ReactNode } from 'react'
import { cn } from '@/utils/cn'

interface SectionCardProps {
  title: string
  subtitle?: string
  extra?: ReactNode
  tone?: 'official' | 'evidence' | 'customer' | 'ai' | 'neutral'
  children: ReactNode
}

const toneClass: Record<NonNullable<SectionCardProps['tone']>, string> = {
  official: 'border-slate-200 bg-white',
  evidence: 'border-emerald-100 bg-white',
  customer: 'border-teal-100 bg-teal-50/40',
  ai: 'border-indigo-100 bg-indigo-50/30',
  neutral: 'border-slate-200 bg-white',
}

export function SectionCard({
  title,
  subtitle,
  extra,
  tone = 'neutral',
  children,
}: SectionCardProps) {
  return (
    <section className={cn('overflow-hidden rounded-2xl border shadow-sm', toneClass[tone])}>
      <div className="flex items-start justify-between gap-3 border-b border-slate-100/80 px-4 py-3">
        <div className="min-w-0">
          <h2 className="text-[15px] font-semibold text-slate-900">{title}</h2>
          {subtitle ? (
            <p className="mt-0.5 text-[12px] leading-5 text-slate-500">{subtitle}</p>
          ) : null}
        </div>
        {extra ? <div className="shrink-0">{extra}</div> : null}
      </div>
      <div className="px-4 py-4">{children}</div>
    </section>
  )
}

export function FactRow({
  label,
  children,
}: {
  label: string
  children: ReactNode
}) {
  return (
    <div className="grid grid-cols-[96px_1fr] gap-x-3 gap-y-1 border-b border-slate-100 py-2.5 last:border-b-0 sm:grid-cols-[120px_1fr]">
      <div className="text-[12px] leading-6 text-slate-500">{label}</div>
      <div className="break-words text-[13px] leading-6 text-slate-800">{children}</div>
    </div>
  )
}
