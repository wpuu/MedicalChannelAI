import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Database,
  ExternalLink,
  Loader2,
  Pencil,
  Plus,
  Power,
  Radar,
  RefreshCw,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  Trash2,
} from 'lucide-react'
import {
  DiscoveryRadarError,
  discoveryRadarErrorMessage,
  scanDiscoverySource,
  type DiscoveryRadarResult,
  type DiscoverySourceKind,
} from '@/services/discoveryRadarApi'
import {
  discoverySourceHealth,
  loadDiscoveryWorkspace,
  newDiscoverySourceId,
  recordDiscoveryFailure,
  recordDiscoverySuccess,
  saveDiscoveryWorkspace,
  type SavedDiscoverySource,
} from '@/services/discoveryRadarStore'
import { formatDateTime } from '@/utils/format'

const SOURCE_KIND_LABELS: Record<DiscoverySourceKind, string> = {
  HOSPITAL_OFFICIAL: '医院官网',
  GOVERNMENT_PROCUREMENT: '政府采购',
  PUBLIC_RESOURCE: '公共资源交易',
  HEALTH_AUTHORITY: '卫健/主管部门',
  OTHER_OFFICIAL: '其他官方渠道',
}

const SIGNAL_LABELS: Record<string, string> = {
  DEMAND_RESEARCH: '需求调研',
  SUPPLIER_RECRUITMENT: '供应商征集',
  TEST_ENTERPRISE_RECRUITMENT: '测试企业征集',
  ARGUMENTATION_INVITATION: '论证邀请',
  PURCHASE_INTENTION: '采购意向',
  OTHER_PREPROCUREMENT: '其他前期窗口',
}

const HEALTH_LABELS = {
  UNTESTED: { text: '未测试', className: 'bg-slate-100 text-slate-600' },
  HEALTHY: { text: '渠道正常', className: 'bg-emerald-50 text-emerald-700' },
  LOW_YIELD: { text: '连续低产出', className: 'bg-amber-50 text-amber-800' },
  REVIEW: { text: '建议检查', className: 'bg-rose-50 text-rose-700' },
} as const

function normalizeSourceUrl(value: string) {
  const parsed = new URL(value.trim())
  if (parsed.protocol !== 'https:' || parsed.username || parsed.password) throw new Error('URL_INVALID')
  parsed.hash = ''
  if (parsed.pathname !== '/') parsed.pathname = parsed.pathname.replace(/\/+$/, '') || '/'
  return parsed.toString()
}

export function DiscoveryRadarPage() {
  const [workspace, setWorkspace] = useState(() => loadDiscoveryWorkspace())
  const [busySource, setBusySource] = useState<string | 'ALL' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [formName, setFormName] = useState('')
  const [formUrl, setFormUrl] = useState('')
  const [formKind, setFormKind] = useState<DiscoverySourceKind>('HOSPITAL_OFFICIAL')
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    saveDiscoveryWorkspace(workspace)
  }, [workspace])

  const enabledSources = useMemo(() => workspace.sources.filter((source) => source.enabled), [workspace.sources])
  const rows = useMemo(
    () => workspace.sources
      .map((source) => workspace.results[source.id])
      .filter(Boolean) as DiscoveryRadarResult[],
    [workspace.results, workspace.sources],
  )

  const summary = useMemo(() => {
    const scores = rows.map((row) => row.discovery_score).filter((value): value is number => typeof value === 'number')
    return {
      hospitals: new Set(enabledSources.map((source) => source.name)).size,
      channels: enabledSources.length,
      anchors: rows.reduce((sum, row) => sum + row.analyzed_anchor_count, 0),
      candidates: rows.reduce((sum, row) => sum + row.candidate_count, 0),
      knownHits: rows.reduce((sum, row) => sum + row.known_verified_hit_count, 0),
      novel: rows.reduce(
        (sum, row) => sum + row.candidates.filter((item) => item.verification_status === 'DISCOVERED_UNVERIFIED').length,
        0,
      ),
      aiCalls: rows.filter((row) => row.ai_called).length,
      reused: rows.filter((row) => !row.ai_called).length,
      score: scores.length ? Math.round((scores.reduce((sum, value) => sum + value, 0) / scores.length) * 10) / 10 : null,
    }
  }, [enabledSources, rows])

  const scanOne = async (sourceId: string, options?: { preserveBusy?: boolean; forceAi?: boolean }) => {
    const source = workspace.sources.find((item) => item.id === sourceId)
    if (!source || !source.enabled) return false
    if (!options?.preserveBusy) setBusySource(sourceId)
    setError(null)
    try {
      const result = await scanDiscoverySource(source, workspace.results[sourceId], options?.forceAi === true)
      setWorkspace((current) => ({
        ...current,
        results: { ...current.results, [sourceId]: result },
        stats: { ...current.stats, [sourceId]: recordDiscoverySuccess(current.stats[sourceId], result) },
      }))
      return true
    } catch (cause) {
      const code = cause instanceof DiscoveryRadarError ? cause.code : 'UNKNOWN'
      setWorkspace((current) => ({
        ...current,
        stats: { ...current.stats, [sourceId]: recordDiscoveryFailure(current.stats[sourceId], code) },
      }))
      setError(`${source.name}：${discoveryRadarErrorMessage(cause)}`)
      return false
    } finally {
      if (!options?.preserveBusy) setBusySource(null)
    }
  }

  const scanAll = async () => {
    if (!enabledSources.length) {
      setError('请先添加并启用至少一个医院或公开渠道')
      return
    }
    setBusySource('ALL')
    setError(null)
    for (const source of enabledSources) {
      await scanOne(source.id, { preserveBusy: true })
    }
    setBusySource(null)
  }

  const resetForm = () => {
    setEditingId(null)
    setFormName('')
    setFormUrl('')
    setFormKind('HOSPITAL_OFFICIAL')
    setFormError(null)
  }

  const saveSource = () => {
    setFormError(null)
    const name = formName.replace(/\s+/g, ' ').trim()
    if (!name || name.length > 100) {
      setFormError('请填写医院或机构名称')
      return
    }
    let url: string
    try {
      url = normalizeSourceUrl(formUrl)
    } catch {
      setFormError('请填写公开可访问的 HTTPS 官方栏目地址')
      return
    }

    const duplicate = workspace.sources.find((source) => source.url === url && source.id !== editingId)
    if (duplicate) {
      setFormError(`该渠道已存在：${duplicate.name}`)
      return
    }

    const now = new Date().toISOString()
    setWorkspace((current) => {
      if (editingId) {
        const existing = current.sources.find((source) => source.id === editingId)
        if (!existing) return current
        const changed = existing.name !== name || existing.url !== url || existing.kind !== formKind
        return {
          ...current,
          sources: current.sources.map((source) => source.id === editingId
            ? { ...source, name, url, kind: formKind, origin: 'USER', updated_at: now }
            : source),
          results: changed
            ? Object.fromEntries(Object.entries(current.results).filter(([key]) => key !== editingId))
            : current.results,
          stats: changed
            ? Object.fromEntries(Object.entries(current.stats).filter(([key]) => key !== editingId))
            : current.stats,
        }
      }
      const source: SavedDiscoverySource = {
        id: newDiscoverySourceId(),
        name,
        url,
        kind: formKind,
        enabled: true,
        origin: 'USER',
        created_at: now,
        updated_at: now,
      }
      return { ...current, sources: [...current.sources, source] }
    })
    resetForm()
  }

  const editSource = (source: SavedDiscoverySource) => {
    setEditingId(source.id)
    setFormName(source.name)
    setFormUrl(source.url)
    setFormKind(source.kind)
    setFormError(null)
  }

  const toggleSource = (sourceId: string) => {
    setWorkspace((current) => ({
      ...current,
      sources: current.sources.map((source) => source.id === sourceId
        ? { ...source, enabled: !source.enabled, updated_at: new Date().toISOString() }
        : source),
    }))
  }

  const deleteSource = (sourceId: string) => {
    setWorkspace((current) => ({
      ...current,
      sources: current.sources.filter((source) => source.id !== sourceId),
      results: Object.fromEntries(Object.entries(current.results).filter(([key]) => key !== sourceId)),
      stats: Object.fromEntries(Object.entries(current.stats).filter(([key]) => key !== sourceId)),
    }))
    if (editingId === sourceId) resetForm()
  }

  const clearSavedResults = () => {
    setWorkspace((current) => ({ ...current, results: {}, stats: {} }))
  }

  return (
    <div className="space-y-4">
      <section className="overflow-hidden rounded-3xl bg-slate-950 px-4 py-5 text-white shadow-lg sm:px-6 sm:py-7">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <div className="mb-3 inline-flex items-center gap-1.5 rounded-full border border-white/15 bg-white/10 px-2.5 py-1 text-[11px] font-medium text-teal-100">
              <Radar className="h-3.5 w-3.5" /> AI情报雷达 · 用户控制扫描范围
            </div>
            <h2 className="text-[22px] font-semibold leading-8 sm:text-3xl">你决定扫哪些医院，AI只分析真实公开入口</h2>
            <p className="mt-2 max-w-2xl text-[13px] leading-6 text-slate-300 sm:text-[14px]">
              每次扫描都会先重新读取官网。页面内容指纹没变化时直接复用已保存结果，不重复调用AI；只有公开页面发生变化或你强制重分析时才重新调用AI。
            </p>
          </div>
          <button
            type="button"
            disabled={busySource !== null || enabledSources.length === 0}
            onClick={() => void scanAll()}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-teal-400 px-4 py-2.5 text-[13px] font-semibold text-slate-950 transition hover:bg-teal-300 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busySource === 'ALL' ? <Loader2 className="h-4 w-4 animate-spin" /> : <ScanSearch className="h-4 w-4" />}
            扫描已启用 {enabledSources.length} 个渠道
          </button>
        </div>
      </section>

      <section className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7 sm:gap-3">
        {[
          ['医院/机构', summary.hospitals, '用户当前启用'],
          ['公开渠道', summary.channels, '可增删停用'],
          ['分析链接', summary.anchors, '真实官方链接'],
          ['AI候选', summary.candidates, '前期窗口候选'],
          ['新候选', summary.novel, '仍待独立核验'],
          ['复用缓存', summary.reused, `本轮AI调用 ${summary.aiCalls}`],
          ['AI发现分', summary.score ?? '—', '仅有已知样本时评分'],
        ].map(([label, value, hint]) => (
          <div key={String(label)} className="rounded-2xl border border-slate-200 bg-white px-3 py-3 shadow-sm">
            <p className="text-[11px] text-slate-500">{label}</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-950">{value}</p>
            <p className="mt-0.5 text-[10px] leading-4 text-slate-400">{hint}</p>
          </div>
        ))}
      </section>

      {error ? <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-[12px] text-amber-900">{error}</div> : null}

      <section className="rounded-2xl border border-slate-200 bg-white p-3.5 shadow-sm sm:p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <Database className="h-4 w-4 text-teal-600" />
              <h3 className="text-[14px] font-semibold text-slate-900">医院与公开渠道管理</h3>
            </div>
            <p className="mt-1 text-[11px] leading-5 text-slate-500">
              初始3个渠道只是验证模板，不是商机结果。你可以删除、停用、替换，或继续增加任意数量的医院官方采购页、政府采购页、公共资源交易页等。
            </p>
          </div>
          {Object.keys(workspace.results).length ? (
            <button type="button" onClick={clearSavedResults} className="text-[11px] text-slate-500 hover:text-slate-900">清空已保存扫描结果</button>
          ) : null}
        </div>

        <div className="mt-3 grid gap-2 md:grid-cols-[1.05fr_1.5fr_0.8fr_auto]">
          <input
            value={formName}
            onChange={(event) => setFormName(event.target.value)}
            placeholder="医院/机构名称"
            className="min-h-11 rounded-xl border border-slate-200 px-3 text-[13px] outline-none focus:border-teal-400"
          />
          <input
            value={formUrl}
            onChange={(event) => setFormUrl(event.target.value)}
            placeholder="https://官方采购/公告栏目地址"
            inputMode="url"
            className="min-h-11 rounded-xl border border-slate-200 px-3 text-[13px] outline-none focus:border-teal-400"
          />
          <select
            value={formKind}
            onChange={(event) => setFormKind(event.target.value as DiscoverySourceKind)}
            className="min-h-11 rounded-xl border border-slate-200 bg-white px-3 text-[13px] outline-none focus:border-teal-400"
          >
            {Object.entries(SOURCE_KIND_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={saveSource}
              className="inline-flex min-h-11 flex-1 items-center justify-center gap-1.5 rounded-xl bg-slate-950 px-3 text-[12px] font-semibold text-white hover:bg-slate-800"
            >
              {editingId ? <Pencil className="h-3.5 w-3.5" /> : <Plus className="h-3.5 w-3.5" />}
              {editingId ? '保存修改' : '添加渠道'}
            </button>
            {editingId ? <button type="button" onClick={resetForm} className="min-h-11 rounded-xl border border-slate-200 px-3 text-[11px] text-slate-600">取消</button> : null}
          </div>
        </div>
        {formError ? <p className="mt-2 text-[11px] text-rose-600">{formError}</p> : null}

        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          {workspace.sources.map((source) => {
            const result = workspace.results[source.id]
            const stats = workspace.stats[source.id]
            const health = HEALTH_LABELS[discoverySourceHealth(stats)]
            const busy = busySource === source.id || busySource === 'ALL'
            return (
              <article key={source.id} className={`rounded-2xl border p-3.5 ${source.enabled ? 'border-slate-200 bg-white' : 'border-slate-200 bg-slate-50 opacity-75'}`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <h4 className="text-[13px] font-semibold text-slate-900">{source.name}</h4>
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[9px] text-slate-600">{SOURCE_KIND_LABELS[source.kind]}</span>
                      <span className={`rounded-full px-2 py-0.5 text-[9px] ${health.className}`}>{health.text}</span>
                      {source.origin === 'STARTER' ? <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[9px] text-indigo-700">初始模板</span> : null}
                    </div>
                    <a href={source.url} target="_blank" rel="noreferrer" className="mt-1 block truncate text-[10px] text-slate-400 hover:text-teal-700">{source.url}</a>
                  </div>
                  <button
                    type="button"
                    disabled={busySource !== null || !source.enabled}
                    onClick={() => void scanOne(source.id)}
                    className="inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-lg border border-teal-200 bg-teal-50 px-2.5 py-1.5 text-[11px] font-medium text-teal-800 hover:bg-teal-100 disabled:opacity-50"
                  >
                    {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Radar className="h-3.5 w-3.5" />}
                    {result ? '检查更新' : '首次扫描'}
                  </button>
                </div>

                {result ? (
                  <div className="mt-3 rounded-xl bg-slate-50 px-3 py-2.5">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-slate-500">
                      <span>链接 {result.analyzed_anchor_count}</span>
                      <span>候选 {result.candidate_count}</span>
                      <span>发现分 {result.discovery_score ?? '—'}</span>
                      <span className={result.ai_called ? 'text-indigo-700' : 'text-emerald-700'}>
                        {result.ai_called ? '官网有变化 · AI已分析' : '官网未变化 · 复用保存结果'}
                      </span>
                    </div>
                    <p className="mt-1 text-[9px] text-slate-400">官网检查 {formatDateTime(result.checked_at)} · AI分析 {formatDateTime(result.analyzed_at)}</p>
                  </div>
                ) : (
                  <p className="mt-3 text-[10px] leading-5 text-slate-400">没有预置扫描结果。首次扫描后结果会保存；以后先比对官网内容指纹。</p>
                )}

                {stats ? (
                  <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[9px] text-slate-400">
                    <span>检查 {stats.scan_count} 次</span>
                    <span>AI调用 {stats.ai_call_count} 次</span>
                    <span>缓存复用 {stats.cache_hit_count} 次</span>
                    <span>累计候选 {stats.total_candidate_count}</span>
                    {stats.consecutive_failure_count >= 2 ? <span className="text-rose-600">连续失败 {stats.consecutive_failure_count} 次，建议检查或停用</span> : null}
                    {stats.consecutive_zero_candidate_count >= 3 ? <span className="text-amber-700">连续3次以上无候选，可观察是否为低价值渠道</span> : null}
                  </div>
                ) : null}

                <div className="mt-3 flex flex-wrap gap-2">
                  {result ? (
                    <button
                      type="button"
                      disabled={busySource !== null || !source.enabled}
                      onClick={() => void scanOne(source.id, { forceAi: true })}
                      className="inline-flex min-h-8 items-center gap-1 rounded-lg border border-slate-200 px-2.5 text-[10px] text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                    >
                      <RefreshCw className="h-3 w-3" /> 强制AI重分析
                    </button>
                  ) : null}
                  <button type="button" onClick={() => editSource(source)} className="inline-flex min-h-8 items-center gap-1 rounded-lg border border-slate-200 px-2.5 text-[10px] text-slate-600 hover:bg-slate-50">
                    <Pencil className="h-3 w-3" /> 修改
                  </button>
                  <button type="button" onClick={() => toggleSource(source.id)} className="inline-flex min-h-8 items-center gap-1 rounded-lg border border-slate-200 px-2.5 text-[10px] text-slate-600 hover:bg-slate-50">
                    <Power className="h-3 w-3" /> {source.enabled ? '停用' : '启用'}
                  </button>
                  <button type="button" onClick={() => deleteSource(source.id)} className="inline-flex min-h-8 items-center gap-1 rounded-lg border border-rose-100 px-2.5 text-[10px] text-rose-600 hover:bg-rose-50">
                    <Trash2 className="h-3 w-3" /> 删除
                  </button>
                </div>
              </article>
            )
          })}
        </div>
      </section>

      {rows.some((row) => row.candidates.length > 0) ? (
        <section className="rounded-2xl border border-slate-200 bg-white p-3.5 shadow-sm sm:p-4">
          <div className="flex items-start gap-2">
            <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-indigo-500" />
            <div>
              <h3 className="text-[14px] font-semibold text-slate-900">已保存的AI发现结果</h3>
              <p className="mt-0.5 text-[11px] leading-5 text-slate-500">结果按渠道保存。官网链接集合没变化时不会重复调用AI；新候选仍需独立官方事实核验。</p>
            </div>
          </div>
          <div className="mt-3 divide-y divide-slate-100">
            {rows.flatMap((row) => row.candidates.map((candidate) => ({ ...candidate, source_id: row.source_id, source_name: row.source_name }))).map((candidate) => (
              <div key={`${candidate.source_id}:${candidate.url}`} className="py-3 first:pt-0 last:pb-0">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-600">{candidate.source_name}</span>
                  <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] text-indigo-700">{SIGNAL_LABELS[candidate.signal_type] ?? '前期窗口'}</span>
                  {candidate.verification_status === 'KNOWN_VERIFIED' ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] text-emerald-700"><ShieldCheck className="h-3 w-3" /> 独立核验已命中</span>
                  ) : (
                    <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] text-amber-800">AI新候选 · 待核验</span>
                  )}
                </div>
                <a href={candidate.url} target="_blank" rel="noreferrer" className="mt-1.5 inline-flex items-start gap-1 text-[13px] font-medium leading-5 text-slate-900 hover:text-teal-700">
                  {candidate.title}<ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                </a>
                <p className="mt-1 text-[11px] leading-5 text-slate-500">{candidate.reason}</p>
                {candidate.opportunity_id ? (
                  <Link to={`/opportunity/${encodeURIComponent(candidate.opportunity_id)}`} className="mt-2 inline-flex min-h-9 items-center rounded-lg bg-emerald-50 px-3 py-1.5 text-[11px] font-semibold text-emerald-800 ring-1 ring-emerald-200 hover:bg-emerald-100">打开已核验商机 →</Link>
                ) : null}
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <section className="flex items-start gap-2 rounded-2xl border border-teal-100 bg-teal-50 px-3 py-3 text-[11px] leading-5 text-teal-950 sm:px-4">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
        <p>
          获取机制：用户决定医院和渠道；服务端只访问公开 HTTPS 地址，并拒绝内网地址、跨域跳转和模型编造链接。演示版扫描结果先保存在当前浏览器；Pilot 账号数据库接入后再升级为账号级云端持久化，不改变发现逻辑。
        </p>
      </section>
    </div>
  )
}
