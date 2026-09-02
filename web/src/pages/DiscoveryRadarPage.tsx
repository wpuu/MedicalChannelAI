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
  Upload,
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
  mergeDiscoveryFindings,
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

function sourceFromLine(line: string, kind: DiscoverySourceKind) {
  const pieces = line.split('|').map((item) => item.trim())
  if (pieces.length !== 2 || !pieces[0] || !pieces[1]) return null
  try {
    return { name: pieces[0].slice(0, 100), url: normalizeSourceUrl(pieces[1]), kind }
  } catch {
    return null
  }
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
  const [bulkOpen, setBulkOpen] = useState(false)
  const [bulkText, setBulkText] = useState('')
  const [bulkKind, setBulkKind] = useState<DiscoverySourceKind>('HOSPITAL_OFFICIAL')

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
  const findings = useMemo(
    () => Object.values(workspace.findings).sort((a, b) => Date.parse(b.last_seen_at) - Date.parse(a.last_seen_at)),
    [workspace.findings],
  )

  const summary = useMemo(() => {
    const scores = rows.map((row) => row.discovery_score).filter((value): value is number => typeof value === 'number')
    return {
      hospitals: new Set(enabledSources.map((source) => source.name)).size,
      channels: enabledSources.length,
      anchors: rows.reduce((sum, row) => sum + row.analyzed_anchor_count, 0),
      currentCandidates: rows.reduce((sum, row) => sum + row.candidate_count, 0),
      savedFindings: findings.length,
      novel: findings.filter((item) => item.verification_status === 'DISCOVERED_UNVERIFIED').length,
      activeFindings: findings.filter((item) => item.active_in_latest_scan).length,
      score: scores.length ? Math.round((scores.reduce((sum, value) => sum + value, 0) / scores.length) * 10) / 10 : null,
    }
  }, [enabledSources, findings, rows])

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
        findings: mergeDiscoveryFindings(current.findings, result),
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
            ? { ...source, name, url, kind: formKind, updated_at: now }
            : source),
          results: changed
            ? Object.fromEntries(Object.entries(current.results).filter(([key]) => key !== editingId))
            : current.results,
          stats: changed
            ? Object.fromEntries(Object.entries(current.stats).filter(([key]) => key !== editingId))
            : current.stats,
          findings: changed
            ? Object.fromEntries(Object.entries(current.findings).filter(([, item]) => item.source_id !== editingId))
            : current.findings,
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

  const importBulkSources = () => {
    setFormError(null)
    const lines = bulkText.split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
    if (!lines.length) {
      setFormError('批量导入为空')
      return
    }
    const parsed = lines.map((line) => sourceFromLine(line, bulkKind))
    const invalidCount = parsed.filter((item) => !item).length
    if (invalidCount) {
      setFormError(`有 ${invalidCount} 行格式不正确。每行应为：医院/机构名称 | https://官方栏目地址`)
      return
    }
    const rows = parsed.filter(Boolean) as Array<{ name: string; url: string; kind: DiscoverySourceKind }>
    const currentUrls = new Set(workspace.sources.map((source) => source.url))
    const uniqueRows = rows.filter((row, index) => !currentUrls.has(row.url) && rows.findIndex((item) => item.url === row.url) === index)
    if (!uniqueRows.length) {
      setFormError('这些渠道已经存在，没有新增项')
      return
    }
    const now = new Date().toISOString()
    setWorkspace((current) => ({
      ...current,
      sources: [
        ...current.sources,
        ...uniqueRows.map((row): SavedDiscoverySource => ({
          id: newDiscoverySourceId(),
          ...row,
          enabled: true,
          origin: 'USER',
          created_at: now,
          updated_at: now,
        })),
      ],
    }))
    setBulkText('')
    setBulkOpen(false)
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
      findings: Object.fromEntries(Object.entries(current.findings).filter(([, item]) => item.source_id !== sourceId)),
    }))
    if (editingId === sourceId) resetForm()
  }

  const clearSavedResults = () => {
    setWorkspace((current) => ({ ...current, results: {}, stats: {}, findings: {} }))
  }

  return (
    <div className="space-y-4">
      <section className="overflow-hidden rounded-3xl bg-slate-950 px-4 py-5 text-white shadow-lg sm:px-6 sm:py-7">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <div className="mb-3 inline-flex items-center gap-1.5 rounded-full border border-white/15 bg-white/10 px-2.5 py-1 text-[11px] font-medium text-teal-100">
              <Radar className="h-3.5 w-3.5" /> AI情报雷达 · 扫描范围由用户维护
            </div>
            <h2 className="text-[22px] font-semibold leading-8 sm:text-3xl">先填医院和公开渠道，再让AI检查哪里真的有新机会</h2>
            <p className="mt-2 max-w-2xl text-[13px] leading-6 text-slate-300 sm:text-[14px]">
              系统不预置商机，也不把任何医院写死成生产范围。每次先检查真实公开页面；链接集合没变化就复用保存结果，不重复调用AI。
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
          ['医院/机构', summary.hospitals, '当前启用'],
          ['公开渠道', summary.channels, '可随时增删'],
          ['分析链接', summary.anchors, '最近一次真实官网'],
          ['当前候选', summary.currentCandidates, '最近扫描仍可见'],
          ['累计保存', summary.savedFindings, `当前仍可见 ${summary.activeFindings}`],
          ['AI新候选', summary.novel, '独立核验前不发布'],
          ['AI发现分', summary.score ?? '—', '仅当前可见已知样本'],
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
              新工作区默认没有医院。你自己填写真实官方栏目；一个医院也可以配置多个公开入口。政府采购、公共资源交易等跨医院渠道也可以单独加入。
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <button type="button" onClick={() => setBulkOpen((value) => !value)} className="inline-flex items-center gap-1 text-[11px] text-teal-700 hover:text-teal-900"><Upload className="h-3.5 w-3.5" />批量导入</button>
            {Object.keys(workspace.results).length ? (
              <button type="button" onClick={clearSavedResults} className="text-[11px] text-slate-500 hover:text-slate-900">清空扫描历史</button>
            ) : null}
          </div>
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

        {bulkOpen ? (
          <div className="mt-3 rounded-xl border border-teal-100 bg-teal-50/50 p-3">
            <p className="text-[11px] font-medium text-teal-950">批量导入医院/机构</p>
            <p className="mt-1 text-[10px] leading-4 text-teal-800">每行格式：医院/机构名称 | https://官方栏目地址。下面选择的渠道类型应用到本批次。</p>
            <textarea
              value={bulkText}
              onChange={(event) => setBulkText(event.target.value)}
              rows={5}
              placeholder={'某医院 | https://example-hospital.cn/purchase\n另一医院 | https://example2.cn/notice'}
              className="mt-2 w-full rounded-xl border border-teal-100 bg-white px-3 py-2 text-[12px] leading-5 outline-none focus:border-teal-400"
            />
            <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-center">
              <select value={bulkKind} onChange={(event) => setBulkKind(event.target.value as DiscoverySourceKind)} className="min-h-10 rounded-lg border border-teal-100 bg-white px-3 text-[11px]">
                {Object.entries(SOURCE_KIND_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
              <button type="button" onClick={importBulkSources} className="min-h-10 rounded-lg bg-teal-700 px-3 text-[11px] font-semibold text-white hover:bg-teal-800">导入并加入扫描范围</button>
            </div>
          </div>
        ) : null}
        {formError ? <p className="mt-2 text-[11px] text-rose-600">{formError}</p> : null}

        {workspace.sources.length === 0 ? (
          <div className="mt-4 rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center">
            <p className="text-[13px] font-medium text-slate-700">当前扫描范围为空</p>
            <p className="mt-1 text-[11px] leading-5 text-slate-400">先添加一个真实医院采购栏目，或批量导入你要关注的医院。添加后再扫描。</p>
          </div>
        ) : (
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
                    <p className="mt-3 text-[10px] leading-5 text-slate-400">首次扫描后保存结果；以后先比对官网链接指纹，只有变化时才再次调用AI。</p>
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
                    <button type="button" onClick={() => editSource(source)} className="inline-flex min-h-8 items-center gap-1 rounded-lg border border-slate-200 px-2.5 text-[10px] text-slate-600 hover:bg-slate-50"><Pencil className="h-3 w-3" /> 修改</button>
                    <button type="button" onClick={() => toggleSource(source.id)} className="inline-flex min-h-8 items-center gap-1 rounded-lg border border-slate-200 px-2.5 text-[10px] text-slate-600 hover:bg-slate-50"><Power className="h-3 w-3" /> {source.enabled ? '停用' : '启用'}</button>
                    <button type="button" onClick={() => deleteSource(source.id)} className="inline-flex min-h-8 items-center gap-1 rounded-lg border border-rose-100 px-2.5 text-[10px] text-rose-600 hover:bg-rose-50"><Trash2 className="h-3 w-3" /> 删除</button>
                  </div>
                </article>
              )
            })}
          </div>
        )}
      </section>

      {findings.length > 0 ? (
        <section className="rounded-2xl border border-slate-200 bg-white p-3.5 shadow-sm sm:p-4">
          <div className="flex items-start gap-2">
            <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-indigo-500" />
            <div>
              <h3 className="text-[14px] font-semibold text-slate-900">累计保存的AI发现</h3>
              <p className="mt-0.5 text-[11px] leading-5 text-slate-500">新一轮扫描不会覆盖旧发现；同一链接自动去重并更新最后出现时间。离开当前官网列表的历史发现仍保留。</p>
            </div>
          </div>
          <div className="mt-3 divide-y divide-slate-100">
            {findings.map((candidate) => (
              <div key={candidate.finding_key} className="py-3 first:pt-0 last:pb-0">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-600">{candidate.source_name}</span>
                  <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] text-indigo-700">{SIGNAL_LABELS[candidate.signal_type] ?? '前期窗口'}</span>
                  {candidate.verification_status === 'KNOWN_VERIFIED' ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] text-emerald-700"><ShieldCheck className="h-3 w-3" /> 独立核验已命中</span>
                  ) : (
                    <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] text-amber-800">AI新候选 · 待核验</span>
                  )}
                  <span className={`rounded-full px-2 py-0.5 text-[10px] ${candidate.active_in_latest_scan ? 'bg-teal-50 text-teal-700' : 'bg-slate-50 text-slate-500'}`}>
                    {candidate.active_in_latest_scan ? '最近扫描仍可见' : '历史已保存'}
                  </span>
                </div>
                <a href={candidate.url} target="_blank" rel="noreferrer" className="mt-1.5 inline-flex items-start gap-1 text-[13px] font-medium leading-5 text-slate-900 hover:text-teal-700">
                  {candidate.title}<ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                </a>
                <p className="mt-1 text-[11px] leading-5 text-slate-500">{candidate.reason}</p>
                <p className="mt-1 text-[9px] text-slate-400">首次发现 {formatDateTime(candidate.first_seen_at)} · 最后出现 {formatDateTime(candidate.last_seen_at)} · 命中 {candidate.times_seen} 次</p>
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
          真实边界：实时产品默认不带医院清单，扫描范围由用户维护；服务端只访问公开 HTTPS 地址，并拒绝内网地址、跨域跳转和模型编造链接。演示版把公开渠道和扫描历史保存在当前浏览器；Pilot 再升级为账号级云端持久化。
        </p>
      </section>
    </div>
  )
}
