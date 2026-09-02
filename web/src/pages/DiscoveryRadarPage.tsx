import { useMemo, useState } from 'react'
import { ExternalLink, Loader2, Radar, ScanSearch, ShieldCheck, Sparkles } from 'lucide-react'
import {
  discoveryRadarErrorMessage,
  scanDiscoverySource,
  type DiscoveryRadarResult,
  type DiscoverySourceId,
} from '@/services/discoveryRadarApi'
import { formatDateTime } from '@/utils/format'

const SOURCES: Array<{ id: DiscoverySourceId; name: string; hint: string }> = [
  { id: 'TMUGH', name: '天津医科大学总医院', hint: '采购信息官方入口' },
  { id: 'TJNOTHOP', name: '天津市天津医院', hint: '医院新闻/采购调研入口' },
  { id: 'TEDA', name: '天津泰达医院', hint: '设备需求与采购信息入口' },
]

const SIGNAL_LABELS: Record<string, string> = {
  DEMAND_RESEARCH: '需求调研',
  SUPPLIER_RECRUITMENT: '供应商征集',
  TEST_ENTERPRISE_RECRUITMENT: '测试企业征集',
  ARGUMENTATION_INVITATION: '论证邀请',
  PURCHASE_INTENTION: '采购意向',
  OTHER_PREPROCUREMENT: '其他前期窗口',
}

export function DiscoveryRadarPage() {
  const [results, setResults] = useState<Partial<Record<DiscoverySourceId, DiscoveryRadarResult>>>({})
  const [busySource, setBusySource] = useState<DiscoverySourceId | 'ALL' | null>(null)
  const [error, setError] = useState<string | null>(null)

  const rows = useMemo(() => Object.values(results).filter(Boolean) as DiscoveryRadarResult[], [results])
  const summary = useMemo(() => ({
    anchors: rows.reduce((sum, row) => sum + row.analyzed_anchor_count, 0),
    candidates: rows.reduce((sum, row) => sum + row.candidate_count, 0),
    knownHits: rows.reduce((sum, row) => sum + row.known_verified_hit_count, 0),
    novel: rows.reduce(
      (sum, row) => sum + row.candidates.filter((item) => item.verification_status === 'DISCOVERED_UNVERIFIED').length,
      0,
    ),
  }), [rows])

  const scanOne = async (sourceId: DiscoverySourceId, preserveBusy = false) => {
    if (!preserveBusy) setBusySource(sourceId)
    setError(null)
    try {
      const result = await scanDiscoverySource(sourceId)
      setResults((current) => ({ ...current, [sourceId]: result }))
      return true
    } catch (cause) {
      setError(discoveryRadarErrorMessage(cause))
      return false
    } finally {
      if (!preserveBusy) setBusySource(null)
    }
  }

  const scanAll = async () => {
    setBusySource('ALL')
    setError(null)
    for (const source of SOURCES) {
      const ok = await scanOne(source.id, true)
      if (!ok) break
    }
    setBusySource(null)
  }

  return (
    <div className="space-y-4">
      <section className="overflow-hidden rounded-3xl bg-slate-950 px-4 py-5 text-white shadow-lg sm:px-6 sm:py-7">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <div className="mb-3 inline-flex items-center gap-1.5 rounded-full border border-white/15 bg-white/10 px-2.5 py-1 text-[11px] font-medium text-teal-100">
              <Radar className="h-3.5 w-3.5" />
              AI情报雷达 · 影子挖掘
            </div>
            <h2 className="text-[22px] font-semibold leading-8 sm:text-3xl">不给AI预置商机，让它自己扫医院官网</h2>
            <p className="mt-2 max-w-2xl text-[13px] leading-6 text-slate-300 sm:text-[14px]">
              每次点击都会重新读取医院官方入口。AI只能从这次真实抓到的链接中挑前期机会；编造链接会被程序直接丢弃。
            </p>
          </div>
          <button
            type="button"
            disabled={busySource !== null}
            onClick={() => void scanAll()}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-teal-400 px-4 py-2.5 text-[13px] font-semibold text-slate-950 transition hover:bg-teal-300 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busySource === 'ALL' ? <Loader2 className="h-4 w-4 animate-spin" /> : <ScanSearch className="h-4 w-4" />}
            扫描全部3个官方入口
          </button>
        </div>
      </section>

      {rows.length > 0 ? (
        <section className="grid grid-cols-2 gap-2 sm:grid-cols-4 sm:gap-3">
          {[
            ['本次分析链接', summary.anchors, '真实官方链接'],
            ['AI候选', summary.candidates, '前期窗口候选'],
            ['已知核验命中', summary.knownHits, '与独立事实层吻合'],
            ['新候选', summary.novel, '仍待独立核验'],
          ].map(([label, value, hint]) => (
            <div key={String(label)} className="rounded-2xl border border-slate-200 bg-white px-3 py-3 shadow-sm sm:px-4">
              <p className="text-[11px] text-slate-500">{label}</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-950">{value}</p>
              <p className="mt-0.5 text-[10px] leading-4 text-slate-400">{hint}</p>
            </div>
          ))}
        </section>
      ) : null}

      {error ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-[12px] text-amber-900">{error}</div>
      ) : null}

      <section className="grid gap-3 lg:grid-cols-3">
        {SOURCES.map((source) => {
          const result = results[source.id]
          const busy = busySource === source.id || busySource === 'ALL'
          return (
            <article key={source.id} className="rounded-2xl border border-slate-200 bg-white p-3.5 shadow-sm sm:p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="text-[14px] font-semibold text-slate-900">{source.name}</h3>
                  <p className="mt-0.5 text-[11px] text-slate-400">{source.hint}</p>
                </div>
                <button
                  type="button"
                  disabled={busySource !== null}
                  onClick={() => void scanOne(source.id)}
                  className="inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-lg border border-teal-200 bg-teal-50 px-2.5 py-1.5 text-[11px] font-medium text-teal-800 hover:bg-teal-100 disabled:opacity-50"
                >
                  {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Radar className="h-3.5 w-3.5" />}
                  {result ? '重新扫描' : '实时扫描'}
                </button>
              </div>

              {result ? (
                <div className="mt-3 space-y-2.5">
                  <div className="grid grid-cols-3 gap-1.5 text-center">
                    <div className="rounded-lg bg-slate-50 px-1.5 py-2">
                      <p className="text-[16px] font-semibold text-slate-900">{result.analyzed_anchor_count}</p>
                      <p className="text-[9px] text-slate-400">分析链接</p>
                    </div>
                    <div className="rounded-lg bg-slate-50 px-1.5 py-2">
                      <p className="text-[16px] font-semibold text-slate-900">{result.candidate_count}</p>
                      <p className="text-[9px] text-slate-400">AI候选</p>
                    </div>
                    <div className="rounded-lg bg-slate-50 px-1.5 py-2">
                      <p className="text-[16px] font-semibold text-slate-900">{result.discovery_score ?? '—'}</p>
                      <p className="text-[9px] text-slate-400">已知样本分</p>
                    </div>
                  </div>
                  <p className="text-[10px] text-slate-400">扫描于 {formatDateTime(result.scanned_at)}</p>
                </div>
              ) : (
                <div className="mt-4 rounded-xl border border-dashed border-slate-200 bg-slate-50 px-3 py-4 text-center text-[11px] leading-5 text-slate-400">
                  点击后才读取官网，本页不预置扫描结果。
                </div>
              )}
            </article>
          )
        })}
      </section>

      {rows.some((row) => row.candidates.length > 0) ? (
        <section className="rounded-2xl border border-slate-200 bg-white p-3.5 shadow-sm sm:p-4">
          <div className="flex items-start gap-2">
            <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-indigo-500" />
            <div>
              <h3 className="text-[14px] font-semibold text-slate-900">AI这次认为值得进入核验队列的链接</h3>
              <p className="mt-0.5 text-[11px] leading-5 text-slate-500">“新候选”只是发现结果，不会自动进入正式商机池。</p>
            </div>
          </div>
          <div className="mt-3 divide-y divide-slate-100">
            {rows.flatMap((row) => row.candidates.map((candidate) => ({ ...candidate, source_name: row.source_name }))).map((candidate) => (
              <div key={candidate.url} className="py-3 first:pt-0 last:pb-0">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-600">{candidate.source_name}</span>
                  <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] text-indigo-700">{SIGNAL_LABELS[candidate.signal_type] ?? '前期窗口'}</span>
                  {candidate.verification_status === 'KNOWN_VERIFIED' ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] text-emerald-700">
                      <ShieldCheck className="h-3 w-3" /> 独立核验已命中
                    </span>
                  ) : (
                    <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] text-amber-800">AI新候选 · 待核验</span>
                  )}
                </div>
                <a
                  href={candidate.url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-1.5 inline-flex items-start gap-1 text-[13px] font-medium leading-5 text-slate-900 hover:text-teal-700"
                >
                  {candidate.title}
                  <ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                </a>
                <p className="mt-1 text-[11px] leading-5 text-slate-500">{candidate.reason}</p>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <section className="flex items-start gap-2 rounded-2xl border border-teal-100 bg-teal-50 px-3 py-3 text-[11px] leading-5 text-teal-950 sm:px-4">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
        <p>
          安全边界：AI只能从本次官网抓到的真实链接中选择；模型编造链接会被拒绝。所有“AI新候选”必须再次经过官方事实核验，才能进入今日商机和客户个性化排序。
        </p>
      </section>
    </div>
  )
}
