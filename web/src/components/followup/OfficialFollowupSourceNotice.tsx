import { ExternalLink, SearchCheck } from 'lucide-react'

type OfficialFollowupSourceNoticeProps = {
  qualityFlags: string[] | null | undefined
  projectName: string | null | undefined
  productNames?: Array<string | null | undefined>
}

const OFFICIAL_FOLLOWUP_SOURCE_PREFIX = 'OFFICIAL_FOLLOWUP_SOURCE='
const TIANJIN_GPC = 'TIANJIN_GPC'
const CEB_PUBLIC_SERVICE = 'CEB_PUBLIC_SERVICE'

function officialFollowupSource(flags: string[] | null | undefined): string | null {
  for (const flag of flags ?? []) {
    if (!flag.startsWith(OFFICIAL_FOLLOWUP_SOURCE_PREFIX)) continue
    const source = flag.slice(OFFICIAL_FOLLOWUP_SOURCE_PREFIX.length).trim()
    if (source === TIANJIN_GPC || source === CEB_PUBLIC_SERVICE) return source
  }
  return null
}

function preferredSearchTerm(
  projectName: string | null | undefined,
  productNames: Array<string | null | undefined> | undefined,
): string | null {
  const product = (productNames ?? []).find((value) => Boolean(value?.trim()))?.trim()
  return product || projectName?.trim() || null
}

export function OfficialFollowupSourceNotice({
  qualityFlags,
  projectName,
  productNames,
}: OfficialFollowupSourceNoticeProps) {
  const source = officialFollowupSource(qualityFlags)
  if (!source) return null

  const searchTerm = preferredSearchTerm(projectName, productNames)
  const isTianjinGpc = source === TIANJIN_GPC
  const label = isTianjinGpc
    ? '天津市政采网 / 天津市政府采购中心'
    : '中国招标投标公共服务平台（CEB）'
  const href = isTianjinGpc
    ? 'https://tjgpc.zwfwb.tj.gov.cn/'
    : 'https://ctbpsp.com/#/'

  return (
    <div
      data-official-followup-source={source}
      className={`mt-2 rounded-lg border px-2.5 py-2 ${
        isTianjinGpc
          ? 'border-teal-200 bg-teal-50/70 text-teal-950'
          : 'border-amber-200 bg-amber-50/80 text-amber-950'
      }`}
    >
      <div className="flex flex-wrap items-center gap-2 text-[11px] font-semibold">
        <SearchCheck className="h-3.5 w-3.5 shrink-0" />
        <span>医院官方指定后续平台：{label}</span>
        <span className="rounded-full border border-current/20 bg-white/60 px-1.5 py-0.5 text-[10px]">
          {isTianjinGpc ? '已纳入定向自动补搜' : '当前需人工核验'}
        </span>
      </div>
      <p className="mt-1 text-[10px] leading-4 opacity-90">
        {isTianjinGpc
          ? '系统会用采购意向中的产品/项目主题做有界补搜；是否属于同一项目仍以正式公告原文和人工核对为准。'
          : '当前没有可验证的 CEB 自动详情适配器；自动未发现不代表没有正式公告，请人工打开官方平台核对。'}
      </p>
      {searchTerm ? (
        <p className="mt-1 text-[10px] leading-4 opacity-80">建议核查关键词：{searchTerm}</p>
      ) : null}
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        className="mt-1.5 inline-flex min-h-7 items-center gap-1 rounded-md border border-current/20 bg-white/70 px-2 py-1 text-[10px] font-medium hover:bg-white"
        title="仅打开官方平台，不会自动改变跟进状态"
      >
        打开官方平台核验
        <ExternalLink className="h-3 w-3" />
      </a>
      <p className="mt-1 text-[9px] leading-4 opacity-70">
        打开链接只是人工核验动作，不会自动标记为已联系、已跟进或确认采购意向与正式项目的关联。
      </p>
    </div>
  )
}
