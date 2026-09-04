import { Info } from 'lucide-react'

export function isPreMarketSignal(
  lifecycleStage: string | null | undefined,
  recommendationMode?: string | null,
): boolean {
  return recommendationMode === 'PRE_MARKET_SIGNAL' ||
    String(lifecycleStage || '').trim().toUpperCase() === 'PROCUREMENT_INTENT'
}

export function PreMarketSignalNotice({
  lifecycleStage,
  recommendationMode,
  compact = false,
}: {
  lifecycleStage: string | null | undefined
  recommendationMode?: string | null
  compact?: boolean
}) {
  if (!isPreMarketSignal(lifecycleStage, recommendationMode)) return null

  return (
    <div className={`flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 text-amber-950 ${
      compact ? 'px-2.5 py-2 text-[11px] leading-5' : 'px-3 py-2.5 text-[12px] leading-5'
    }`}>
      <Info className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
      <div>
        <p className="font-semibold">提前布局信号，不是正式招标窗口</p>
        <p className="mt-0.5 text-amber-900">
          这是采购意向/供应商征询类早期信号。当前不能按“已经可以报名或投标”处理；适合先确认院内需求、厂家资源、产品匹配和参数路线，并持续关注后续正式公告。
        </p>
      </div>
    </div>
  )
}
