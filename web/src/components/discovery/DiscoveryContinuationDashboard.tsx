import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ExternalLink, Loader2, ScanSearch, ShieldCheck } from 'lucide-react'
import { useDiscoveryWorkspace } from '@/components/discovery/DiscoveryWorkspaceProvider'
import {
  discoveryContinuationErrorMessage,
  scanDiscoveryContinuation,
} from '@/services/discoveryContinuationApi'
import {
  mergeDiscoveryContinuationIntoWorkspace,
} from '@/services/discoveryContinuationFindings'
import {
  appendContinuationSegment,
  continuationEligible,
  continuationLedgerSummary,
  loadContinuationLedger,
  type DiscoveryContinuationLedger,
} from '@/services/discoveryContinuationLedger'
import type { DiscoveryWorkspace, SavedDiscoverySource } from '@/services/discoveryRadarStore'
import type { DiscoveryRadarResult } from '@/services/discoveryRadarApi'
import { formatDateTime } from '@/utils/format'

type EligibleSource = {
  source: SavedDiscoverySource
  root: DiscoveryRadarResult
}

const SIGNAL_LABELS: Record<string, string> = {
  DEMAND_RESEARCH: '需求调研',
  SUPPLIER_RECRUITMENT: '供应商征集',
  TEST_ENTERPRISE_RECRUITMENT: '测试企业征集',
  ARGUMENTATION_INVITATION: '论证邀请',
  PURCHASE_INTENTION: '采购意向',
  OTHER_PREPROCUREMENT: '其他前期窗口',
}

function eligibleRows(workspace: DiscoveryWorkspace): EligibleSource[] {
  return workspace.sources
    .filter((source) => source.enabled)
    .map((source) => ({ source, root: workspace.results[source.id] }))
    .filter((row): row is EligibleSource => Boolean(row.root && continuationEligible(row.root)))
}

export function DiscoveryContinuationDashboard() {
  const { workspace, setWorkspace, storageReady } = useDiscoveryWorkspace()
  const [ledgers, setLedgers] = useState<Record<string, DiscoveryContinuationLedger>>({})
  const [busySource, setBusySource] = useState<string | null>(null)
  const [errors, setErrors] = useState<Record<string, string>>({})

  const eligible = useMemo(() => eligibleRows(workspace), [workspace])
  const ledgerKey = useMemo(
    () => eligible.map(({ source, root }) => `${source.id}:${root.content_fingerprint}`).join('|'),
    [eligible],
  )

  useEffect(() => {
    let active = true
    void Promise.all(
      eligible.map(async ({ source, root }) => [source.id, await loadContinuationLedger(source, root)] as const),
    ).then((rows) => {
      if (!active) return
      setLedgers(Object.fromEntries(rows))
      setWorkspace((current) => {
        let next = current
        for (const [, ledger] of rows) {
          for (const segment of ledger.segments) {
            next = mergeDiscoveryContinuationIntoWorkspace(next, segment)
          }
        }
        return next
      })
    })
    return () => { active = false }
    // Rehydrate only when the eligible source/root fingerprint set changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ledgerKey])

  const totals = useMemo(() => {
    return eligible.reduce((acc, { source }) => {
      const ledger = ledgers[source.id]
      if (!ledger) return acc
      const summary = continuationLedgerSummary(ledger)
      acc.segments += summary.segment_count
      acc.anchors += summary.analyzed_anchor_count
      acc.candidates += summary.candidate_count
      if (summary.exhausted) acc.exhausted += 1
      return acc
    }, { segments: 0, anchors: 0, candidates: 0, exhausted: 0 })
  }, [eligible, ledgers])

  const scanNext = async (source: SavedDiscoverySource, root: DiscoveryRadarResult) => {
    if (busySource) return
    setBusySource(source.id)
    setErrors((current) => ({ ...current, [source.id]: '' }))
    try {
      const currentLedger = ledgers[source.id] ?? await loadContinuationLedger(source, root)
      const currentSummary = continuationLedgerSummary(currentLedger)
      if (!currentSummary.can_continue) {
        setErrors((current) => ({ ...current, [source.id]: currentSummary.exhausted ? '该续扫链已经到达末页' : '当前根扫描已达到安全续扫段上限，请改用更具体的官方栏目入口' }))
        return
      }
      const segment = await scanDiscoveryContinuation(source, root, currentLedger.segments)
      const nextLedger = await appendContinuationSegment(currentLedger, segment)
      setLedgers((current) => ({ ...current, [source.id]: nextLedger }))
      setWorkspace((current) => mergeDiscoveryContinuationIntoWorkspace(current, segment))
    } catch (cause) {
      setErrors((current) => ({ ...current, [source.id]: discoveryContinuationErrorMessage(cause) }))
    } finally {
      setBusySource(null)
    }
  }

  if (!storageReady || eligible.length === 0) return null

  return (
    <section className="rounded-2xl border border-amber-200 bg-amber-50/40 p-3.5 shadow-sm sm:p-4">
      <div className="flex items-start gap-2">
        <ScanSearch className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
        <div>
          <h3 className="text-[14px] font-semibold text-slate-900">深分页补扫发现</h3>
          <p className="mt-1 max-w-3xl text-[11px] leading-5 text-slate-600">
            这里只出现根扫描已经确认“仍有更深分页”或“80条窗口被截断”的真实公开渠道。续扫仍保存在独立 IndexedDB segment 账本，不覆盖首页增量快照；候选同时按来源与官方URL幂等合并进统一累计发现账本。
          </p>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-4 gap-2">
        <div className="rounded-xl bg-white px-3 py-2 ring-1 ring-amber-100"><p className="text-[9px] text-slate-400">可续扫渠道</p><p className="mt-1 text-xl font-semibold tabular-nums text-slate-900">{eligible.length}</p></div>
        <div className="rounded-xl bg-white px-3 py-2 ring-1 ring-amber-100"><p className="text-[9px] text-slate-400">已保存段</p><p className="mt-1 text-xl font-semibold tabular-nums text-slate-900">{totals.segments}</p></div>
        <div className="rounded-xl bg-white px-3 py-2 ring-1 ring-amber-100"><p className="text-[9px] text-slate-400">补扫新链接</p><p className="mt-1 text-xl font-semibold tabular-nums text-slate-900">{totals.anchors}</p></div>
        <div className="rounded-xl bg-white px-3 py-2 ring-1 ring-amber-100"><p className="text-[9px] text-slate-400">补扫候选</p><p className="mt-1 text-xl font-semibold tabular-nums text-slate-900">{totals.candidates}</p></div>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        {eligible.map(({ source, root }) => {
          const ledger = ledgers[source.id]
          const summary = ledger ? continuationLedgerSummary(ledger) : null
          const last = ledger?.segments.at(-1)
          const busy = busySource === source.id
          const candidates = ledger?.segments.flatMap((segment) => segment.candidates) ?? []
          return (
            <article key={`${source.id}:${root.content_fingerprint}`} className="rounded-2xl border border-amber-200 bg-white p-3.5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h4 className="text-[13px] font-semibold text-slate-900">{source.name}</h4>
                  <p className="mt-1 truncate text-[10px] text-slate-400">{source.url}</p>
                </div>
                <button
                  type="button"
                  disabled={busySource !== null || !summary?.can_continue}
                  onClick={() => void scanNext(source, root)}
                  className="inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-lg bg-amber-600 px-3 text-[11px] font-semibold text-white hover:bg-amber-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ScanSearch className="h-3.5 w-3.5" />}
                  {summary?.exhausted ? '已到末页' : summary?.can_continue === false ? '已到续扫上限' : '安全续扫下一段'}
                </button>
              </div>

              <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-slate-500">
                <span>根窗口 {root.analyzed_anchor_count} 条</span>
                <span>续扫 {summary?.segment_count ?? 0}/5 段</span>
                <span>新增链接 {summary?.analyzed_anchor_count ?? 0}</span>
                <span>候选 {summary?.candidate_count ?? 0}</span>
                {summary?.exhausted ? <span className="font-medium text-emerald-700">已确认到达末页</span> : <span className="text-amber-700">仍可继续补扫</span>}
              </div>
              {last ? <p className="mt-1 text-[9px] text-slate-400">最近续扫 {formatDateTime(last.checked_at)} · 本段读取 {last.page_urls.length} 页 · 新链接 {last.analyzed_anchor_count}</p> : <p className="mt-1 text-[9px] text-slate-400">尚未补扫。第一次会从根扫描最后已检查页重新探测，再沿官方明确“下一页”向后推进。</p>}
              {errors[source.id] ? <p className="mt-2 rounded-lg bg-rose-50 px-2.5 py-2 text-[10px] text-rose-700">{errors[source.id]}</p> : null}

              {candidates.length ? (
                <div className="mt-3 space-y-2 border-t border-slate-100 pt-3">
                  {candidates.slice(-8).reverse().map((candidate) => (
                    <div key={`${source.id}:${candidate.url}`} className="rounded-xl bg-slate-50 px-3 py-2.5">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[9px] text-indigo-700">{SIGNAL_LABELS[candidate.signal_type] ?? '前期窗口'}</span>
                        {candidate.verification_status === 'KNOWN_VERIFIED' ? <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[9px] text-emerald-700"><ShieldCheck className="h-3 w-3" /> 独立核验已命中</span> : <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[9px] text-amber-800">AI新候选 · 待核验</span>}
                      </div>
                      <a href={candidate.url} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-start gap-1 text-[11px] font-medium leading-5 text-slate-900 hover:text-teal-700">{candidate.title}<ExternalLink className="mt-0.5 h-3 w-3 shrink-0" /></a>
                      <p className="mt-0.5 text-[10px] leading-4 text-slate-500">{candidate.reason}</p>
                      {candidate.opportunity_id ? <Link to={`/opportunity/${encodeURIComponent(candidate.opportunity_id)}`} className="mt-2 inline-flex min-h-8 items-center rounded-lg bg-emerald-50 px-2.5 text-[10px] font-semibold text-emerald-800 ring-1 ring-emerald-200">打开已核验商机 →</Link> : null}
                    </div>
                  ))}
                </div>
              ) : null}
            </article>
          )
        })}
      </div>

      <p className="mt-3 text-[10px] leading-4 text-amber-900">
        根扫描与补扫现在共享同一个工作区内存状态和持久化队列；补扫候选会按 source + 官方URL 无损并入“累计保存的AI发现”。独立 segment 账本仍只负责分页恢复位置、根指纹和补扫审计，不会改写根扫描 anchor 快照。
      </p>
    </section>
  )
}
