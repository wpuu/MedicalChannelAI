import { cn } from '@/utils/cn'
import { EmptyValue } from './EmptyValue'

export function StageBadge({ stage }: { stage: string | null }) {
  if (!stage) return <EmptyValue />
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-md border px-1.5 py-0.5 text-[12px]',
        'border-slate-200 bg-slate-50 text-slate-700',
      )}
    >
      {stage}
    </span>
  )
}

export function VerifiedBadge({ status }: { status: 'VERIFIED' | 'UNVERIFIED' | 'PARTIAL' }) {
  if (status === 'VERIFIED') {
    return (
      <span className="inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-800">
        已核实
      </span>
    )
  }
  if (status === 'PARTIAL') {
    return (
      <span className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-800">
        部分核实
      </span>
    )
  }
  return (
    <span className="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-medium text-slate-600">
      未核实
    </span>
  )
}

export function SourceTag({
  tone,
  children,
}: {
  tone: 'official' | 'evidence' | 'customer' | 'ai'
  children: string
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-md px-1.5 py-0.5 text-[11px] font-medium',
        tone === 'official' && 'bg-slate-100 text-slate-600',
        tone === 'evidence' && 'bg-emerald-50 text-emerald-800',
        tone === 'customer' && 'bg-teal-50 text-teal-800',
        tone === 'ai' && 'bg-indigo-50 text-indigo-800',
      )}
    >
      {children}
    </span>
  )
}

export function FollowupChip({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[11px] text-slate-600">
      {label}
    </span>
  )
}
