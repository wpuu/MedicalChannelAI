import { Info } from 'lucide-react'

const EXPECTED_WINDOW_PREFIX = 'EXPECTED_PROCUREMENT_MONTH_WINDOW_TEXT='

type ProcurementWindowPhase = 'BEFORE' | 'ACTIVE' | 'AFTER' | 'UNKNOWN'

export function isPreMarketSignal(
  lifecycleStage: string | null | undefined,
  recommendationMode?: string | null,
): boolean {
  return recommendationMode === 'PRE_MARKET_SIGNAL' ||
    String(lifecycleStage || '').trim().toUpperCase() === 'PROCUREMENT_INTENT'
}

export function expectedProcurementWindowText(
  qualityFlags: string[] | null | undefined,
): string | null {
  const flag = qualityFlags?.find((item) => item.startsWith(EXPECTED_WINDOW_PREFIX))
  if (!flag) return null
  return flag.slice(EXPECTED_WINDOW_PREFIX.length).trim() || null
}

function shanghaiYearMonth(now: Date): { year: number; month: number } {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: 'numeric',
  }).formatToParts(now)
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]))
  return {
    year: Number(values.year),
    month: Number(values.month),
  }
}

function parsedExpectedWindow(value: string): { start: number; end: number } | null {
  const text = value.trim()
  const range = text.match(/^(20\d{2})年\s*(\d{1,2})\s*月?\s*[-—~～至到]\s*(\d{1,2})月$/)
  if (range) {
    const year = Number(range[1])
    const startMonth = Number(range[2])
    const endMonth = Number(range[3])
    if (startMonth >= 1 && startMonth <= 12 && endMonth >= startMonth && endMonth <= 12) {
      return {
        start: year * 12 + startMonth,
        end: year * 12 + endMonth,
      }
    }
  }

  const single = text.match(/^(20\d{2})年\s*(\d{1,2})月$/)
  if (!single) return null
  const year = Number(single[1])
  const month = Number(single[2])
  if (month < 1 || month > 12) return null
  return {
    start: year * 12 + month,
    end: year * 12 + month,
  }
}

export function expectedProcurementWindowPhase(
  expectedWindow: string | null | undefined,
  now = new Date(),
): ProcurementWindowPhase {
  if (!expectedWindow) return 'UNKNOWN'
  const parsed = parsedExpectedWindow(expectedWindow)
  if (!parsed) return 'UNKNOWN'
  const current = shanghaiYearMonth(now)
  const currentMonth = current.year * 12 + current.month
  if (currentMonth < parsed.start) return 'BEFORE'
  if (currentMonth > parsed.end) return 'AFTER'
  return 'ACTIVE'
}

function phaseCopy(phase: ProcurementWindowPhase): { title: string; action: string } {
  if (phase === 'AFTER') {
    return {
      title: '预计采购月份已过 · 先核查正式公告',
      action: '官方预计采购月份已经过去。应优先核查是否已经发布正式采购、招标或新的调研公告；若仍未发现，再决定继续监控或通过公告公开渠道确认项目进度。',
    }
  }
  if (phase === 'ACTIVE') {
    return {
      title: '预计采购窗口已到 · 重点盯正式公告',
      action: '当前已经进入官方预计采购月份。应把“核查正式公告、确认厂家资源、产品匹配和参数路线”提升为当前任务，而不是继续只做远期观察。',
    }
  }
  if (phase === 'BEFORE') {
    return {
      title: '提前布局信号，不是正式招标窗口',
      action: '预计采购窗口尚未到。适合先确认院内需求、厂家资源、产品匹配和参数路线，并设置后续检查节点。',
    }
  }
  return {
    title: '提前布局信号，不是正式招标窗口',
    action: '适合先确认院内需求、厂家资源、产品匹配和参数路线，并持续关注后续正式公告。',
  }
}

export function PreMarketSignalNotice({
  lifecycleStage,
  recommendationMode,
  qualityFlags,
  compact = false,
}: {
  lifecycleStage: string | null | undefined
  recommendationMode?: string | null
  qualityFlags?: string[] | null
  compact?: boolean
}) {
  if (!isPreMarketSignal(lifecycleStage, recommendationMode)) return null
  const expectedWindow = expectedProcurementWindowText(qualityFlags)
  const phase = expectedProcurementWindowPhase(expectedWindow)
  const copy = phaseCopy(phase)

  return (
    <div className={`flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 text-amber-950 ${
      compact ? 'px-2.5 py-2 text-[11px] leading-5' : 'px-3 py-2.5 text-[12px] leading-5'
    }`}>
      <Info className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
      <div>
        <p className="font-semibold">{copy.title}</p>
        <p className="mt-0.5 text-amber-900">
          {expectedWindow ? (
            <span className="font-semibold">官方预计采购时间：{expectedWindow}。 </span>
          ) : null}
          这是采购意向/供应商征询类早期信号，不能按“已经可以报名或投标”处理。{copy.action}
          {expectedWindow ? ' 系统不会把预计月份换算成具体截止日期。' : ''}
        </p>
      </div>
    </div>
  )
}
