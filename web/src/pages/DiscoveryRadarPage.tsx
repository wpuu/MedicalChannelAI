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
  loadDiscoveryWorkspaceDurable,
  mergeDiscoveryFindings,
  newDiscoverySourceId,
  recordDiscoveryFailure,
  recordDiscoverySuccess,
  requestDiscoveryStoragePersistence,
  saveDiscoveryWorkspace,
  type DiscoveryStorageStatus,
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

const MULTI_SCAN_GAP_MS = 2200
const FINDINGS_RENDER_LIMIT = 500

function normalizeSourceUrl(value: string) {
  const parsed = new URL(value.trim())
  if (parsed.protocol !== 'https:' || parsed.username || parsed.password) throw new Error('URL_INVALID')
  parsed.hash = ''
  if (parsed.pathname !== '/') parsed.pathname = parsed.pathname.replace(/\/+$/, '') || '/'
  return parsed.toString()
}

function normalizeScope(value: string) {
  return value.replace(/\s+/g, ' ').trim().slice(0, 40)
}

function sourceScope(source: Pick<SavedDiscoverySource, 'scope'>) {
  return normalizeScope(source.scope) || '未分组'
}

function sourceFromLine(line: string, kind: DiscoverySourceKind, fallbackScope: string) {
  const pieces = line.split('|').map((item) => item.trim())
  const scope = pieces.length === 3 ? normalizeScope(pieces[0]) : normalizeScope(fallbackScope)
  const name = pieces.length === 3 ? pieces[1] : pieces[0]
  const rawUrl = pieces.length === 3 ? pieces[2] : pieces[1]
  if (![2, 3].includes(pieces.length) || !name || !rawUrl) return null
  try {
    return { scope, name: name.slice(0, 100), url: normalizeSourceUrl(rawUrl), kind }
  } catch {
    return null
  }
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function formatBytes(value: number | null) {
  if (value === null || !Number.isFinite(value)) return '—'
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  if (value < 1024 * 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`
  return `${(value / 1024 / 1024 / 1024).toFixed(1)} GB`
}

function cacheStatusText(result: DiscoveryRadarResult) {
  if (result.cache_status === 'FRESH_DELTA_AI') {
    return `新增 ${result.new_anchor_count} / 变更 ${result.changed_anchor_count} · AI仅分析 ${result.ai_analyzed_anchor_count} 条增量`
  }
  if (result.cache_status === 'REUSED_PARTIAL_COVERAGE') return '分页读取不完整 · 沿用上次完整结果'
  if (result.cache_status === 'REUSED_UNCHANGED') return '官网链接未变化 · 未调用AI'
  if (result.cache_status === 'REUSED_NO_NEW_LINKS') return '官网有变化但没有新/变更链接 · 未调用AI'
  return `首次/强制分析 · AI分析 ${result.ai_analyzed_anchor_count} 条`
}

function coverageStatusText(result: DiscoveryRadarResult) {
  if (result.coverage_partial) {
    return `本轮成功读取 ${result.coverage_page_count} 页 / ${result.coverage_scanned_anchor_count} 条链接 · 下一页失败，未用局部结果覆盖完整历史`
  }
  if (result.coverage_page_limit_applied) {
    return `自动检查 ${result.coverage_page_count} 页 · 仍有下一页，已到安全上限`
  }
  if (result.coverage_page_count > 1) return `自动检查 ${result.coverage_page_count} 页 · 已纳入明确下一页`
  if (result.coverage_next_page_detected) return '检测到分页，但本轮未继续扩展'
  return '检查入口页 · 未检测到明确下一页'
}

export function DiscoveryRadarPage() {
  const [workspace, setWorkspace] = useState(() => loadDiscoveryWorkspace())
  const [storageReady, setStorageReady] = useState(false)
  const [storageStatus, setStorageStatus] = useState<DiscoveryStorageStatus | null>(null)
  const [busySource, setBusySource] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [formScope, setFormScope] = useState('天津市')
  const [formName, setFormName] = useState('')
  const [formUrl, setFormUrl] = useState('')
  const [formKind, setFormKind] = useState<DiscoverySourceKind>('HOSPITAL_OFFICIAL')
  const [formError, setFormError] = useState<string | null>(null)
  const [bulkOpen, setBulkOpen] = useState(false)
  const [bulkText, setBulkText] = useState('')
  const [bulkScope, setBulkScope] = useState('天津市')
  const [bulkKind, setBulkKind] = useState<DiscoverySourceKind>('HOSPITAL_OFFICIAL')

  useEffect(() => {
    let active = true
    const fallback = workspace
    void loadDiscoveryWorkspaceDurable(fallback).then(({ workspace: durable, status }) => {
      if (!active) return
      setWorkspace(durable)
      setStorageStatus(status)
      setStorageReady(true)
    })
    return () => { active = false }
    // Hydrate once before allowing scans so an empty bootstrap cannot overwrite durable history.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!storageReady) return
    let active = true
    void saveDiscoveryWorkspace(workspace).then((status) => {
      if (active) setStorageStatus(status)
    })
    return () => { active = false }
  }, [storageReady, workspace])

  const enabledSources = useMemo(() => workspace.sources.filter((source) => source.enabled), [workspace.sources])
  const scopeNames = useMemo(
    () => Array.from(new Set(enabledSources.map(sourceScope))).sort((a, b) => a.localeCompare(b, 'zh-CN')),
    [enabledSources],
  )
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
  const visibleFindings = useMemo(() => findings.slice(0, FINDINGS_RENDER_LIMIT), [findings])

  const summary = useMemo(() => {
    const scores = rows.map((row) => row.discovery_score).filter((value): value is number => typeof value === 'number')
    return {
      scopes: scopeNames.length,
      hospitals: new Set(enabledSources.filter((source) => source.kind === 'HOSPITAL_OFFICIAL').map((source) => source.name)).size,
      channels: enabledSources.length,
      anchors: rows.reduce((sum, row) => sum + row.analyzed_anchor_count, 0),
      currentCandidates: rows.reduce((sum, row) => sum + row.candidate_count, 0),
      savedFindings: findings.length,
      novel: findings.filter((item) => item.verification_status === 'DISCOVERED_UNVERIFIED').length,
      score: scores.length ? Math.round((scores.reduce((sum, value) => sum + value, 0) / scores.length) * 10) / 10 : null,
    }
  }, [enabledSources, findings, rows, scopeNames.length])

  const scanOne = async (sourceId: string, options?: { preserveBusy?: boolean; forceAi?: boolean }) => {
    const source = workspace.sources.find((item) => item.id === sourceId)
    if (!source || !source.enabled || !storageReady) return false
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

  const scanMany = async (sources: SavedDiscoverySource[], busyKey: string) => {
    if (!storageReady) {
      setError('本地发现账本仍在加载，请稍候')
      return
    }
    if (!sources.length) {
      setError('该范围没有已启用的公开渠道')
      return
    }
    setBusySource(busyKey)
    setError(null)
    for (let index = 0; index < sources.length; index += 1) {
      await scanOne(sources[index].id, { preserveBusy: true })
      if (index < sources.length - 1) await sleep(MULTI_SCAN_GAP_MS)
    }
    setBusySource(null)
  }

  const scanAll = async () => scanMany(enabledSources, 'ALL')

  const scanScope = async (scope: string) => {
    const sources = enabledSources.filter((source) => sourceScope(source) === scope)
    await scanMany(sources, `SCOPE:${scope}`)
  }

  const resetForm = () => {
    setEditingId(null)
    setFormScope('天津市')
    setFormName('')
    setFormUrl('')
    setFormKind('HOSPITAL_OFFICIAL')
    setFormError(null)
  }

  const saveSource = () => {
    setFormError(null)
    const scope = normalizeScope(formScope)
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
        const contentChanged = existing.name !== name || existing.url !== url || existing.kind !== formKind
        return {
          ...current,
          sources: current.sources.map((source) => source.id === editingId
            ? { ...source, scope, name, url, kind: formKind, updated_at: now }
            : source),
          results: contentChanged
            ? Object.fromEntries(Object.entries(current.results).filter(([key]) => key !== editingId))
            : current.results,
          stats: contentChanged
            ? Object.fromEntries(Object.entries(current.stats).filter(([key]) => key !== editingId))
            : current.stats,
          findings: contentChanged
            ? Object.fromEntries(Object.entries(current.findings).filter(([, item]) => item.source_id !== editingId))
            : current.findings,
        }
      }
      const source: SavedDiscoverySource = {
        id: newDiscoverySourceId(),
        scope,
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
    const parsed = lines.map((line) => sourceFromLine(line, bulkKind, bulkScope))
    const invalidCount = parsed.filter((item) => !item).length
    if (invalidCount) {
      setFormError(`有 ${invalidCount} 行格式不正确。每行应为：医院/机构名称 | https://官方栏目地址，或 范围 | 医院/机构名称 | https://官方栏目地址`)
      return
    }
    const parsedRows = parsed.filter(Boolean) as Array<{ scope: string; name: string; url: string; kind: DiscoverySourceKind }>
    const currentUrls = new Set(workspace.sources.map((source) => source.url))
    const uniqueRows = parsedRows.filter((row, index) => !currentUrls.has(row.url) && parsedRows.findIndex((item) => item.url === row.url) === index)
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
    setFormScope(source.scope)
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

  const requestPersistence = async () => {
    const granted = await requestDiscoveryStoragePersistence()
    setStorageStatus((current) => current ? { ...current, persistent: granted } : current)
  }

  return (
    <div className="space-y-4">
      <section className="overflow-hidden rounded-3xl bg-slate-950 px-4 py-5 text-white shadow-lg sm:px-6 sm:py-7">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <div className="mb-3 inline-flex items-center gap-1.5 rounded-full border border-white/15 bg-white/10 px-2.5 py-1 text-[11px] font-medium text-teal-100">
              <Radar className="h-3.5 w-3.5" /> AI情报雷达 · 区域增量搜索
            </div>
            <h2 className="text-[22px] font-semibold leading-8 sm:text-3xl">先建立真实公开渠道，再持续只找上次之后的新线索</h2>
            <p className="mt-2 max-w-2xl text-[13px] leading-6 text-slate-300 sm:text-[14px]">
              每次仍会重新检查官网列表，因为不检查就无法知道是否更新；但旧链接不会重复交给AI。只有新增链接或标题发生变化时才做增量AI分析。
            </p>
          </div>
          <button
            type="button"
            disabled={!storageReady || busySource !== null || enabledSources.length === 0}
            onClick={() => void scanAll()}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-teal-400 px-4 py-2.5 text-[13px] font-semibold text-slate-950 transition hover:bg-teal-300 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busySource === 'ALL' ? <Loader2 className="h-4 w-4 animate-spin" /> : <ScanSearch className="h-4 w-4" />}
            扫描全部 {enabledSources.length} 个启用渠道
          </button>
        </div>
      </section>

      <section className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8 sm:gap-3">
        {[
          ['搜索范围', summary.scopes, '例如天津市'],
          ['医院', summary.hospitals, '医院官网来源'],
          ['公开渠道', summary.channels, '可随时增删'],
          ['当前链接', summary.anchors, '最近一次官网窗口'],
          ['当前候选', summary.currentCandidates, '最近扫描仍可见'],
          ['累计保存', summary.savedFindings, `界面显示最近 ${Math.min(summary.savedFindings, FINDINGS_RENDER_LIMIT)}`],
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

      <section className="rounded-2xl border border-indigo-100 bg-indigo-50/50 p-3.5 sm:p-4">
        <div className="flex items-start gap-2">
          <ScanSearch className="mt-0.5 h-4 w-4 shrink-0 text-indigo-600" />
          <div className="min-w-0 flex-1">
            <h3 className="text-[14px] font-semibold text-slate-900">区域大范围增量搜索</h3>
            <p className="mt-1 text-[11px] leading-5 text-slate-600">
              “天津市”不是一次性搜索词，而是一个渠道集合：天津市范围内的医院官网、政府采购、公共资源交易、卫健主管部门等入口都归到同一范围。再次搜索时逐渠道检查更新，只把新增/变更链接交给AI，已经判断过且未变化的链接直接复用。
            </p>
            <p className="mt-1 text-[10px] leading-4 text-slate-500">单个入口如果存在同官方域名、明确标记的“下一页”或 rel=next，当前会安全地再检查 1 页；第2页使用更短的 4 秒读取上限。如果第2页临时失败，不会用残缺的一页结果覆盖上次完整账本。总分析链接仍最多 80 条；大范围扫描按渠道顺序执行，并在渠道之间保留约 2.2 秒间隔。</p>
          </div>
        </div>
        {scopeNames.length ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {scopeNames.map((scope) => {
              const count = enabledSources.filter((source) => sourceScope(source) === scope).length
              const busy = busySource === `SCOPE:${scope}`
              return (
                <button
                  key={scope}
                  type="button"
                  disabled={!storageReady || busySource !== null}
                  onClick={() => void scanScope(scope)}
                  className="inline-flex min-h-10 items-center gap-1.5 rounded-xl border border-indigo-200 bg-white px-3 text-[11px] font-semibold text-indigo-800 hover:bg-indigo-50 disabled:opacity-50"
                >
                  {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Radar className="h-3.5 w-3.5" />}
                  扫描{scope}全部 {count} 个渠道
                </button>
              )
            })}
          </div>
        ) : (
          <p className="mt-3 text-[11px] text-slate-500">先在下面给渠道填写“天津市”等范围标签；范围本身不会凭空生成医院或结果。</p>
        )}
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-3.5 shadow-sm sm:p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-2">
            <Database className="mt-0.5 h-4 w-4 shrink-0 text-teal-600" />
            <div>
              <h3 className="text-[14px] font-semibold text-slate-900">本地发现账本</h3>
              <p className="mt-1 text-[11px] leading-5 text-slate-500">
                大数据不再主要塞进 localStorage。当前优先保存在 IndexedDB；localStorage 只保留轻量启动信息，IndexedDB 不可用时才降级。
              </p>
            </div>
          </div>
          {storageStatus?.persistent === false ? (
            <button type="button" onClick={() => void requestPersistence()} className="min-h-9 rounded-lg border border-slate-200 px-3 text-[10px] text-slate-600 hover:bg-slate-50">请求浏览器长期保留</button>
          ) : null}
        </div>
        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5">
          <div className="rounded-xl bg-slate-50 px-3 py-2"><p className="text-[9px] text-slate-400">状态</p><p className="mt-1 text-[11px] font-medium text-slate-700">{storageReady ? '已加载' : '正在加载'}</p></div>
          <div className="rounded-xl bg-slate-50 px-3 py-2"><p className="text-[9px] text-slate-400">存储方式</p><p className="mt-1 text-[11px] font-medium text-slate-700">{storageStatus?.mode === 'INDEXED_DB' ? 'IndexedDB' : storageStatus ? 'localStorage降级' : '—'}</p></div>
          <div className="rounded-xl bg-slate-50 px-3 py-2"><p className="text-[9px] text-slate-400">本工作区估算</p><p className="mt-1 text-[11px] font-medium text-slate-700">{formatBytes(storageStatus?.workspace_bytes ?? null)}</p></div>
          <div className="rounded-xl bg-slate-50 px-3 py-2"><p className="text-[9px] text-slate-400">当前站点已用/额度</p><p className="mt-1 text-[11px] font-medium text-slate-700">{formatBytes(storageStatus?.origin_usage_bytes ?? null)} / {formatBytes(storageStatus?.origin_quota_bytes ?? null)}</p></div>
          <div className="rounded-xl bg-slate-50 px-3 py-2"><p className="text-[9px] text-slate-400">浏览器持久保留</p><p className="mt-1 text-[11px] font-medium text-slate-700">{storageStatus?.persistent === true ? '已允许' : storageStatus?.persistent === false ? '未保证' : '—'}</p></div>
        </div>
        {storageStatus?.warning ? (
          <p className="mt-2 text-[10px] leading-4 text-amber-700">
            {storageStatus.warning === 'INDEXED_DB_UNAVAILABLE' ? '当前浏览器无法使用 IndexedDB，数据量增大后 localStorage 可能很快触顶。' : '本地数据或站点存储占用已经较高，应尽快迁移到账号级云端持久化。'}
          </p>
        ) : null}
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-3.5 shadow-sm sm:p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <Database className="h-4 w-4 text-teal-600" />
              <h3 className="text-[14px] font-semibold text-slate-900">医院与公开渠道管理</h3>
            </div>
            <p className="mt-1 text-[11px] leading-5 text-slate-500">
              新工作区默认没有医院。用户填写真实官方栏目，并用“天津市”等范围分组；一个医院可以配置多个入口，跨医院的政府采购/公共资源渠道也可以加入同一范围。
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <button type="button" onClick={() => setBulkOpen((value) => !value)} className="inline-flex items-center gap-1 text-[11px] text-teal-700 hover:text-teal-900"><Upload className="h-3.5 w-3.5" />批量导入</button>
            {Object.keys(workspace.results).length ? (
              <button type="button" onClick={clearSavedResults} className="text-[11px] text-slate-500 hover:text-slate-900">清空扫描历史</button>
            ) : null}
          </div>
        </div>

        <div className="mt-3 grid gap-2 md:grid-cols-[0.7fr_1fr_1.45fr_0.85fr_auto]">
          <input value={formScope} onChange={(event) => setFormScope(event.target.value)} placeholder="范围，如 天津市" className="min-h-11 rounded-xl border border-slate-200 px-3 text-[13px] outline-none focus:border-teal-400" />
          <input value={formName} onChange={(event) => setFormName(event.target.value)} placeholder="医院/机构名称" className="min-h-11 rounded-xl border border-slate-200 px-3 text-[13px] outline-none focus:border-teal-400" />
          <input value={formUrl} onChange={(event) => setFormUrl(event.target.value)} placeholder="https://官方采购/公告栏目地址" inputMode="url" className="min-h-11 rounded-xl border border-slate-200 px-3 text-[13px] outline-none focus:border-teal-400" />
          <select value={formKind} onChange={(event) => setFormKind(event.target.value as DiscoverySourceKind)} className="min-h-11 rounded-xl border border-slate-200 bg-white px-3 text-[13px] outline-none focus:border-teal-400">
            {Object.entries(SOURCE_KIND_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <div className="flex gap-2">
            <button type="button" onClick={saveSource} className="inline-flex min-h-11 flex-1 items-center justify-center gap-1.5 rounded-xl bg-slate-950 px-3 text-[12px] font-semibold text-white hover:bg-slate-800">
              {editingId ? <Pencil className="h-3.5 w-3.5" /> : <Plus className="h-3.5 w-3.5" />}{editingId ? '保存修改' : '添加渠道'}
            </button>
            {editingId ? <button type="button" onClick={resetForm} className="min-h-11 rounded-xl border border-slate-200 px-3 text-[11px] text-slate-600">取消</button> : null}
          </div>
        </div>

        {bulkOpen ? (
          <div className="mt-3 rounded-xl border border-teal-100 bg-teal-50/50 p-3">
            <p className="text-[11px] font-medium text-teal-950">批量导入医院/机构</p>
            <p className="mt-1 text-[10px] leading-4 text-teal-800">兼容：医院/机构名称 | https://官方栏目地址；也可直接写：范围 | 医院/机构名称 | https://官方栏目地址。</p>
            <textarea value={bulkText} onChange={(event) => setBulkText(event.target.value)} rows={5} placeholder={'天津市 | 某医院 | https://example-hospital.cn/purchase\n天津市 | 政府采购入口 | https://example.gov.cn/notice'} className="mt-2 w-full rounded-xl border border-teal-100 bg-white px-3 py-2 text-[12px] leading-5 outline-none focus:border-teal-400" />
            <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-center">
              <input value={bulkScope} onChange={(event) => setBulkScope(event.target.value)} placeholder="两列格式的默认范围" className="min-h-10 rounded-lg border border-teal-100 bg-white px-3 text-[11px]" />
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
            <p className="mt-1 text-[11px] leading-5 text-slate-400">先添加真实医院采购栏目或区域级公开入口。范围标签本身不产生结果。</p>
          </div>
        ) : (
          <div className="mt-4 grid gap-3 lg:grid-cols-2">
            {workspace.sources.map((source) => {
              const result = workspace.results[source.id]
              const stats = workspace.stats[source.id]
              const health = HEALTH_LABELS[discoverySourceHealth(stats)]
              const scope = sourceScope(source)
              const busy = busySource === source.id || busySource === 'ALL' || busySource === `SCOPE:${scope}`
              return (
                <article key={source.id} className={`rounded-2xl border p-3.5 ${source.enabled ? 'border-slate-200 bg-white' : 'border-slate-200 bg-slate-50 opacity-75'}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <h4 className="text-[13px] font-semibold text-slate-900">{source.name}</h4>
                        <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[9px] text-indigo-700">{scope}</span>
                        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[9px] text-slate-600">{SOURCE_KIND_LABELS[source.kind]}</span>
                        <span className={`rounded-full px-2 py-0.5 text-[9px] ${health.className}`}>{health.text}</span>
                      </div>
                      <a href={source.url} target="_blank" rel="noreferrer" className="mt-1 block truncate text-[10px] text-slate-400 hover:text-teal-700">{source.url}</a>
                    </div>
                    <button type="button" disabled={!storageReady || busySource !== null || !source.enabled} onClick={() => void scanOne(source.id)} className="inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-lg border border-teal-200 bg-teal-50 px-2.5 py-1.5 text-[11px] font-medium text-teal-800 hover:bg-teal-100 disabled:opacity-50">
                      {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Radar className="h-3.5 w-3.5" />}{result ? '检查更新' : '首次扫描'}
                    </button>
                  </div>

                  {result ? (
                    <div className="mt-3 rounded-xl bg-slate-50 px-3 py-2.5">
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-slate-500">
                        <span>当前链接 {result.analyzed_anchor_count}</span>
                        <span>候选 {result.candidate_count}</span>
                        <span>发现分 {result.discovery_score ?? '—'}</span>
                        <span className={result.ai_called ? 'text-indigo-700' : result.coverage_partial ? 'text-amber-700' : 'text-emerald-700'}>{cacheStatusText(result)}</span>
                      </div>
                      <p className={`mt-1 text-[9px] ${result.coverage_partial || result.coverage_page_limit_applied ? 'text-amber-700' : 'text-slate-400'}`}>{coverageStatusText(result)}</p>
                      <p className="mt-1 text-[9px] text-slate-400">新增 {result.new_anchor_count} · 标题变化 {result.changed_anchor_count} · 移出当前窗口 {result.removed_anchor_count} · 复用旧链接 {result.reused_anchor_count}</p>
                      <p className="mt-1 text-[9px] text-slate-400">官网检查 {formatDateTime(result.checked_at)} · 最近AI分析 {formatDateTime(result.analyzed_at)}</p>
                    </div>
                  ) : (
                    <p className="mt-3 text-[10px] leading-5 text-slate-400">首次扫描保存当前链接快照；以后逐链接比较，新链接和标题变化才交给AI，旧链接不重复分析。明确的同域“下一页”会额外检查1页。</p>
                  )}

                  {stats ? (
                    <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[9px] text-slate-400">
                      <span>检查 {stats.scan_count} 次</span><span>AI调用 {stats.ai_call_count} 次</span><span>缓存复用 {stats.cache_hit_count} 次</span><span>累计候选 {stats.total_candidate_count}</span>
                      {stats.consecutive_failure_count >= 2 ? <span className="text-rose-600">连续失败 {stats.consecutive_failure_count} 次，建议检查或停用</span> : null}
                      {stats.consecutive_zero_candidate_count >= 3 ? <span className="text-amber-700">连续3次以上无候选，可观察是否为低价值渠道</span> : null}
                    </div>
                  ) : null}

                  <div className="mt-3 flex flex-wrap gap-2">
                    {result ? <button type="button" disabled={!storageReady || busySource !== null || !source.enabled} onClick={() => void scanOne(source.id, { forceAi: true })} className="inline-flex min-h-8 items-center gap-1 rounded-lg border border-slate-200 px-2.5 text-[10px] text-slate-600 hover:bg-slate-50 disabled:opacity-50"><RefreshCw className="h-3 w-3" /> 强制AI重分析</button> : null}
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
              <p className="mt-0.5 text-[11px] leading-5 text-slate-500">新一轮扫描不会覆盖旧发现；同一链接自动去重。为避免大量历史拖慢手机界面，这里最多渲染最近 {FINDINGS_RENDER_LIMIT} 条，但本地账本仍保存全部记录。</p>
            </div>
          </div>
          <div className="mt-3 divide-y divide-slate-100">
            {visibleFindings.map((candidate) => (
              <div key={candidate.finding_key} className="py-3 first:pt-0 last:pb-0">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-600">{candidate.source_name}</span>
                  <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] text-indigo-700">{SIGNAL_LABELS[candidate.signal_type] ?? '前期窗口'}</span>
                  {candidate.verification_status === 'KNOWN_VERIFIED' ? <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] text-emerald-700"><ShieldCheck className="h-3 w-3" /> 独立核验已命中</span> : <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] text-amber-800">AI新候选 · 待核验</span>}
                  <span className={`rounded-full px-2 py-0.5 text-[10px] ${candidate.active_in_latest_scan ? 'bg-teal-50 text-teal-700' : 'bg-slate-50 text-slate-500'}`}>{candidate.active_in_latest_scan ? '最近扫描仍可见' : '历史已保存'}</span>
                </div>
                <a href={candidate.url} target="_blank" rel="noreferrer" className="mt-1.5 inline-flex items-start gap-1 text-[13px] font-medium leading-5 text-slate-900 hover:text-teal-700">{candidate.title}<ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0" /></a>
                <p className="mt-1 text-[11px] leading-5 text-slate-500">{candidate.reason}</p>
                <p className="mt-1 text-[9px] text-slate-400">首次发现 {formatDateTime(candidate.first_seen_at)} · 最后出现 {formatDateTime(candidate.last_seen_at)} · 命中 {candidate.times_seen} 次</p>
                {candidate.opportunity_id ? <Link to={`/opportunity/${encodeURIComponent(candidate.opportunity_id)}`} className="mt-2 inline-flex min-h-9 items-center rounded-lg bg-emerald-50 px-3 py-1.5 text-[11px] font-semibold text-emerald-800 ring-1 ring-emerald-200 hover:bg-emerald-100">打开已核验商机 →</Link> : null}
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <section className="flex items-start gap-2 rounded-2xl border border-teal-100 bg-teal-50 px-3 py-3 text-[11px] leading-5 text-teal-950 sm:px-4">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
        <p>
          真实边界：区域搜索只覆盖用户实际维护的公开渠道，不把“天津市”三个字当成全网无遗漏保证；单个入口当前最多分析80个去重官方链接，只有同官方域名、明确标记为 rel=next / “下一页”的分页才会自动再检查1页（最多2页）。若第二页临时超时/失败，有历史时沿用上次完整结果，不把局部页面误判成大量“已消失”；首次扫描则会明确标记本轮覆盖不完整。若仍检测到下一页会提示已到安全上限；JS分页、复杂分页或更深历史仍需独立入口或专用适配器。演示版先用 IndexedDB 保存发现账本；跨设备、后台长期扫描和不可丢失历史仍必须迁到账号级云端。
        </p>
      </section>
    </div>
  )
}
