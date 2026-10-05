import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  ArrowRight,
  BookmarkPlus,
  Building2,
  CalendarClock,
  Check,
  ExternalLink,
  Loader2,
  Phone,
  Radar,
  SearchCheck,
} from 'lucide-react'
import { OfficialFollowupSourceNotice } from '@/components/followup/OfficialFollowupSourceNotice'
import { RemindModal } from '@/components/followup/RemindModal'
import {
  expectedProcurementWindowPhase,
  expectedProcurementWindowText,
  isPreMarketSignal,
} from '@/components/shared/PreMarketSignalNotice'
import { EmptyState, ErrorState } from '@/components/shared/PageStates'
import { useToast } from '@/context/ToastContext'
import { todayActionsService } from '@/services'
import { isAuthRequiredError } from '@/services/apiConfig'
import type { TodayActionCard } from '@/types'
import { formatDateTime, isoDaysFromNow } from '@/utils/format'

const GENERIC_PRODUCT_TERMS = new Set([
  '医疗设备',
  '医疗器械',
  '设备',
  '耗材',
  '试剂',
  '服务',
  '采购项目',
  '设备采购项目',
  '医疗设备采购项目',
  '医疗器械采购项目',
])

const GENERIC_PROJECT_SUBJECTS = new Set([
  '采购项目',
  '医疗设备采购项目',
  '医疗器械采购项目',
  '设备采购项目',
  '服务项目',
])

function normalizeText(value: string | null | undefined): string {
  return String(value || '')
    .toLowerCase()
    .replace(/[\s·•,，。；;：:、()（）【】\[\]《》<>“”"'\/\\_-]+/g, '')
}

function institutionKey(card: TodayActionCard): string {
  return normalizeText(card.facts.hospital ?? card.facts.buyer_name)
}

function productTerms(card: TodayActionCard): string[] {
  const institution = institutionKey(card)
  const values = [
    ...(card.facts.product_categories ?? []),
    ...(card.facts.products ?? []).flatMap((item) => [item.name, item.category]),
  ]
  const result = new Set<string>()
  for (const value of values) {
    let term = normalizeText(value)
    if (!term) continue
    if (institution && term.includes(institution)) term = term.replace(institution, '')
    if (term.length < 2 || GENERIC_PRODUCT_TERMS.has(term)) continue
    result.add(term)
  }
  return [...result]
}

function projectSubject(card: TodayActionCard): string | null {
  const institution = institutionKey(card)
  let subject = normalizeText(card.facts.project_name)
  if (!subject) return null
  if (institution && subject.includes(institution)) subject = subject.replace(institution, '')
  subject = subject.replace(/^采购意向公告(?:20\d{2}年)?第?\d+号?/, '')
  if (subject.length < 6 || GENERIC_PROJECT_SUBJECTS.has(subject)) return null
  return subject
}

function publicationTime(card: TodayActionCard): number | null {
  if (!card.facts.publish_date) return null
  const parsed = Date.parse(card.facts.publish_date)
  return Number.isNaN(parsed) ? null : parsed
}

function matchedTerms(left: TodayActionCard, right: TodayActionCard): string[] {
  const leftTerms = productTerms(left)
  const rightTerms = productTerms(right)
  const matches = new Set<string>()
  for (const leftTerm of leftTerms) {
    for (const rightTerm of rightTerms) {
      const exact = leftTerm === rightTerm
      const contained =
        Math.min(leftTerm.length, rightTerm.length) >= 4 &&
        (leftTerm.includes(rightTerm) || rightTerm.includes(leftTerm))
      if (exact || contained) matches.add(leftTerm.length <= rightTerm.length ? leftTerm : rightTerm)
    }
  }
  return [...matches].slice(0, 3)
}

function successorEvidence(intent: TodayActionCard, candidate: TodayActionCard) {
  const terms = matchedTerms(intent, candidate)
  const intentSubject = projectSubject(intent)
  const candidateSubject = projectSubject(candidate)
  const subjectMatch = Boolean(
    intentSubject && candidateSubject && intentSubject === candidateSubject,
  )
  return { terms, subjectMatch, subject: subjectMatch ? intentSubject : null }
}

function successorCandidates(intent: TodayActionCard, cards: TodayActionCard[]) {
  const institution = institutionKey(intent)
  const intentPublished = publicationTime(intent)
  if (!institution || intentPublished === null) return []

  return cards
    .filter((candidate) => candidate.opportunity_id !== intent.opportunity_id)
    .filter((candidate) => !isPreMarketSignal(candidate.facts.lifecycle_stage, candidate.recommendation_mode))
    .filter((candidate) => institutionKey(candidate) === institution)
    .map((candidate) => ({
      card: candidate,
      published: publicationTime(candidate),
      ...successorEvidence(intent, candidate),
    }))
    .filter((item) => (
      item.published !== null &&
      item.published >= intentPublished &&
      (item.terms.length > 0 || item.subjectMatch)
    ))
    .sort((left, right) => (left.published ?? 0) - (right.published ?? 0))
    .slice(0, 3)
}

function procurementPhase(card: TodayActionCard) {
  return expectedProcurementWindowPhase(expectedProcurementWindowText(card.facts.quality_flags))
}

function phaseOrder(card: TodayActionCard): number {
  const phase = procurementPhase(card)
  if (phase === 'AFTER') return 0
  if (phase === 'ACTIVE') return 1
  if (phase === 'BEFORE') return 2
  return 3
}

function phaseLabel(card: TodayActionCard): string {
  const phase = procurementPhase(card)
  if (phase === 'AFTER') return '预计采购月份已过，优先核查后续公告'
  if (phase === 'ACTIVE') return '已进入预计采购月份，重点盯正式公告'
  if (phase === 'BEFORE') return '预计采购月份未到，继续提前布局'
  return '未结构化出预计采购月份，持续观察'
}

function phaseActions(card: TodayActionCard, hasSuccessor: boolean): string[] {
  if (hasSuccessor) {
    return [
      '已出现满足保守关联规则的后续正式商机候选，先打开正式公告核对采购单位、项目主题、项目编号和截止时间。',
      '核对可参与条件、厂家/渠道资源、授权或维保资质、文件获取方式，并按正式公告的报名/响应/投标窗口执行。',
      '只有人工核对确认后再记录实际业务动作；候选关联本身不等于官方确认“采购意向与正式项目为同一项目”。',
    ]
  }
  const phase = procurementPhase(card)
  if (phase === 'AFTER') {
    return [
      '先查医院官网、政府采购/招标等已核验公开源，看是否已经出现正式采购、招标、调研或延期公告。',
      '公开源仍未发现时，可使用公告公开电话确认项目是否延期、调整或已进入其他采购流程；只记录对方明确回复。',
      '根据核查结果决定继续跟进、设置下一次检查节点或人工归档，不把“没有搜到”解释成项目取消。',
    ]
  }
  if (phase === 'ACTIVE') {
    return [
      '把正式公告核查提升为当前任务，优先确认是否已经开放报名、响应或投标窗口。',
      '同步确认厂家/渠道资源、可供产品或服务能力，以及是否需要授权、维保资质或配套实施资源。',
      '整理与官方采购对象直接相关的参数、品牌/型号替代路线和院内确认问题，避免等正式公告后再从零准备。',
    ]
  }
  if (phase === 'BEFORE') {
    return [
      '先确认可合作厂家、渠道和产品/服务匹配，不把采购意向当成已经开放的订单。',
      '整理需要向院方或厂家确认的参数、使用场景和实施条件，只保留有公开依据或用户确认的事实。',
      '设置接近预计采购月份的下一次检查节点，届时优先核查正式公告。',
    ]
  }
  return [
    '先核对官方原文与采购对象，确认当前公开信息能支持哪些准备动作。',
    '确认厂家/渠道资源和产品匹配，但不要自行推断正式采购时间。',
    '持续观察后续正式公告，并由用户决定是否设置下一次检查节点。',
  ]
}

function formalDeadlineSummary(card: TodayActionCard): string | null {
  const labels: string[] = []
  if (card.facts.registration_deadline) {
    labels.push(`报名截止 ${formatDateTime(card.facts.registration_deadline) ?? card.facts.registration_deadline}`)
  } else if (card.facts.registration_deadline_date) {
    labels.push(`报名截止日期 ${card.facts.registration_deadline_date}（未公布具体时间）`)
  }
  if (card.facts.bid_deadline) {
    labels.push(`投标/响应截止 ${formatDateTime(card.facts.bid_deadline) ?? card.facts.bid_deadline}`)
  }
  return labels.length > 0 ? labels.join(' · ') : null
}

function shanghaiDateFromTimestamp(value: string): string | null {
  const parsed = Date.parse(value)
  if (Number.isNaN(parsed)) return null
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(new Date(parsed))
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]))
  return values.year && values.month && values.day
    ? `${values.year}-${values.month}-${values.day}`
    : null
}

function previousIsoDate(value: string): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
  if (!match) return null
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])))
  if (
    date.getUTCFullYear() !== Number(match[1]) ||
    date.getUTCMonth() + 1 !== Number(match[2]) ||
    date.getUTCDate() !== Number(match[3])
  ) return null
  date.setUTCDate(date.getUTCDate() - 1)
  return [
    date.getUTCFullYear(),
    String(date.getUTCMonth() + 1).padStart(2, '0'),
    String(date.getUTCDate()).padStart(2, '0'),
  ].join('-')
}

type FormalReminderConstraint = {
  maxDate: string
  deadlineHint: string
  canSchedule: boolean
}

function formalReminderConstraint(card: TodayActionCard, now = Date.now()): FormalReminderConstraint | null {
  const candidates: Array<{ at: number; date: string; hint: string }> = []
  const addExact = (value: string | null | undefined, label: string) => {
    if (!value) return
    const at = Date.parse(value)
    const date = shanghaiDateFromTimestamp(value)
    if (Number.isNaN(at) || at <= now || !date) return
    candidates.push({
      at,
      date,
      hint: `${label} ${formatDateTime(value) ?? value}`,
    })
  }
  addExact(card.facts.registration_deadline, '报名截止')
  addExact(card.facts.bid_deadline, '投标/响应截止')

  const registrationDate = card.facts.registration_deadline_date
  if (registrationDate && /^\d{4}-\d{2}-\d{2}$/.test(registrationDate)) {
    const at = Date.parse(`${registrationDate}T23:59:59+08:00`)
    if (!Number.isNaN(at) && at > now) {
      candidates.push({
        at,
        date: registrationDate,
        hint: `报名截止日期 ${registrationDate}（官方未公布具体时间）`,
      })
    }
  }

  candidates.sort((left, right) => left.at - right.at)
  const earliest = candidates[0]
  if (!earliest) return null
  const maxDate = previousIsoDate(earliest.date)
  if (!maxDate) return null
  return {
    maxDate,
    deadlineHint: earliest.hint,
    canSchedule: maxDate >= isoDaysFromNow(1),
  }
}

function reminderSummary(card: TodayActionCard): string | null {
  if (!card.remind_at) return null
  const when = formatDateTime(card.remind_at) ?? card.remind_at
  return `下一步提醒 ${when}`
}

function telHref(value: string | null | undefined): string | null {
  const raw = String(value || '').trim()
  if (!raw || /[、,，;；/]/.test(raw)) return null
  const leadingPlus = raw.startsWith('+')
  const digits = raw.replace(/\D/g, '')
  if (digits.length < 5) return null
  return `tel:${leadingPlus ? '+' : ''}${digits}`
}

export function ProcurementIntentFollowupPage() {
  const navigate = useNavigate()
  const { toast } = useToast()
  const [cards, setCards] = useState<TodayActionCard[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [followBusyId, setFollowBusyId] = useState<string | null>(null)
  const [remindId, setRemindId] = useState<string | null>(null)

  const loadCards = async () => {
    const data = await todayActionsService.getTodayActions({ hydrateFollowups: false })
    setCards(data.opportunity_pool ?? data.cards)
  }

  useEffect(() => {
    let cancelled = false
    void todayActionsService.getTodayActions({ hydrateFollowups: false })
      .then((data) => {
        if (cancelled) return
        setCards(data.opportunity_pool ?? data.cards)
        setError(false)
      })
      .catch((cause) => {
        if (cancelled) return
        if (isAuthRequiredError(cause)) {
          navigate('/login', { replace: true })
          return
        }
        setError(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [navigate])

  const rows = useMemo(() => {
    return cards
      .filter((card) => isPreMarketSignal(card.facts.lifecycle_stage, card.recommendation_mode))
      .map((intent) => ({ intent, successors: successorCandidates(intent, cards) }))
      .sort((left, right) => {
        const successorDiff = Number(right.successors.length > 0) - Number(left.successors.length > 0)
        if (successorDiff !== 0) return successorDiff
        const phaseDiff = phaseOrder(left.intent) - phaseOrder(right.intent)
        if (phaseDiff !== 0) return phaseDiff
        return (publicationTime(right.intent) ?? 0) - (publicationTime(left.intent) ?? 0)
      })
  }, [cards])

  const startFollowup = async (card: TodayActionCard, kind: 'INTENT' | 'FORMAL') => {
    if (card.followup_status !== 'NEW' || followBusyId) return
    setFollowBusyId(card.opportunity_id)
    try {
      await todayActionsService.updateFollowup(card.opportunity_id, { status: 'REVIEWING' })
      setCards((current) => current.map((item) =>
        item.opportunity_id === card.opportunity_id
          ? { ...item, followup_status: 'REVIEWING' }
          : item,
      ))
      toast(
        kind === 'FORMAL'
          ? '正式项目已加入我的跟进；这不会把采购意向与正式项目自动认定为同一项目。'
          : '采购意向已加入我的跟进；提醒时间和下一步行动由你确认后再设置。',
        'success',
      )
    } catch (cause) {
      if (isAuthRequiredError(cause)) {
        navigate('/login', { replace: true })
        return
      }
      toast('加入跟进失败，请重试')
    } finally {
      setFollowBusyId(null)
    }
  }

  const saveNextAction = async (card: TodayActionCard, remindAt: string, nextAction: string): Promise<boolean> => {
    if (card.followup_status === 'NEW' || followBusyId) return false
    setFollowBusyId(card.opportunity_id)
    try {
      await todayActionsService.updateFollowup(card.opportunity_id, {
        status: card.followup_status,
        remind_at: remindAt,
        note: `下次行动：${nextAction}`,
      })
      try {
        await loadCards()
      } catch (cause) {
        if (isAuthRequiredError(cause)) navigate('/login', { replace: true })
        else toast('下一步和提醒已保存，但页面刷新失败，请重新加载。')
        return true
      }
      toast('下一步和提醒已保存；当前销售阶段保持不变。', 'success')
      return true
    } catch (cause) {
      if (isAuthRequiredError(cause)) {
        navigate('/login', { replace: true })
        return false
      }
      toast('下一步保存失败，请重试')
      return false
    } finally {
      setFollowBusyId(null)
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-56 items-center justify-center text-sm text-slate-500">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        正在核查采购意向与后续正式商机…
      </div>
    )
  }
  if (error) {
    return <ErrorState message="采购意向跟进视图加载失败，请稍后重试。" onRetry={() => window.location.reload()} />
  }
  if (rows.length === 0) {
    return <EmptyState title="当前没有可跟进的采购意向" hint="后续核验到新的采购意向后，会在这里自动进入跟进视图。" />
  }

  const reminderCard = remindId
    ? cards.find((item) => item.opportunity_id === remindId) ?? null
    : null
  const reminderIsFormal = Boolean(
    reminderCard &&
    !isPreMarketSignal(reminderCard.facts.lifecycle_stage, reminderCard.recommendation_mode),
  )
  const reminderConstraint = reminderCard && reminderIsFormal
    ? formalReminderConstraint(reminderCard)
    : null

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
        <div className="flex items-start gap-3">
          <Radar className="mt-0.5 h-5 w-5 shrink-0 text-teal-700" />
          <div>
            <h1 className="text-lg font-semibold text-slate-900">采购意向跟进</h1>
            <p className="mt-1 text-[12px] leading-5 text-slate-600">
              系统只用已核验公开事实做保守关联：同一采购单位、后续公告发布时间不早于采购意向，并且结构化产品重合，或去掉采购单位和采购意向公告前缀后的项目主题精确一致。关联结果只是“可能承接的后续项目”，不是官方声明为同一项目，最终仍需人工核对项目编号、科室、产品和公告原文。关联候选不会改变公开优先级或中标判断。
            </p>
          </div>
        </div>
      </section>

      {rows.map(({ intent, successors }) => {
        const buyer = intent.facts.hospital ?? intent.facts.buyer_name ?? '采购单位未提供'
        const expectedWindow = expectedProcurementWindowText(intent.facts.quality_flags)
        const followed = intent.followup_status !== 'NEW'
        const followBusy = followBusyId === intent.opportunity_id
        const actions = phaseActions(intent, successors.length > 0)
        const publicPhone = intent.facts.official_contact?.phone?.trim() || null
        const phoneHref = telHref(publicPhone)
        const intentReminder = reminderSummary(intent)
        return (
          <section key={intent.opportunity_id} className="rounded-2xl border border-slate-200 bg-white px-4 py-4 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 text-[11px] font-medium text-amber-800">
                  <Building2 className="h-3.5 w-3.5" />
                  {buyer}
                </div>
                <h2 className="mt-1 text-[15px] font-semibold leading-6 text-slate-900">
                  {intent.facts.project_name ?? '采购意向名称未提供'}
                </h2>
                <p className="mt-1 text-[12px] leading-5 text-slate-600">
                  {expectedWindow ? `官方预计采购时间：${expectedWindow} · ` : ''}{phaseLabel(intent)}
                </p>
                <OfficialFollowupSourceNotice
                  qualityFlags={intent.facts.quality_flags}
                  projectName={intent.facts.project_name}
                  productNames={(intent.facts.products ?? []).map((item) => item.name)}
                />
                {successors.length > 0 ? (
                  <p className="mt-1 inline-flex rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-800">
                    已出现可能的正式窗口 · 需人工核对
                  </p>
                ) : null}
                {intentReminder ? (
                  <p className="mt-1 text-[11px] font-medium text-teal-700">{intentReminder}</p>
                ) : null}
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={followed || Boolean(followBusyId)}
                  onClick={() => void startFollowup(intent, 'INTENT')}
                  className="inline-flex min-h-8 items-center gap-1 rounded-lg border border-teal-200 bg-teal-50 px-2.5 py-1.5 text-[11px] font-medium text-teal-800 hover:bg-teal-100 disabled:cursor-default disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-500"
                >
                  {followBusy ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : followed ? (
                    <Check className="h-3 w-3" />
                  ) : (
                    <BookmarkPlus className="h-3 w-3" />
                  )}
                  {followBusy ? '正在加入…' : followed ? '已在我的跟进' : '加入采购意向跟进'}
                </button>
                {followed ? (
                  <button
                    type="button"
                    disabled={Boolean(followBusyId)}
                    onClick={() => setRemindId(intent.opportunity_id)}
                    className="inline-flex min-h-8 items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                  >
                    <CalendarClock className="h-3 w-3" />
                    安排下一步
                  </button>
                ) : null}
                {phoneHref && publicPhone ? (
                  <a
                    href={phoneHref}
                    className="inline-flex min-h-8 items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
                    title="拨号只打开电话，不会自动记录为已联系"
                  >
                    <Phone className="h-3 w-3" />
                    公告公开电话 {publicPhone}
                  </a>
                ) : null}
                <Link
                  to={`/opportunity/${encodeURIComponent(intent.opportunity_id)}`}
                  className="inline-flex min-h-8 items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
                >
                  查看意向原文与详情
                  <ExternalLink className="h-3 w-3" />
                </Link>
              </div>
            </div>

            <div className={`mt-3 rounded-xl border px-3 py-3 ${successors.length > 0 ? 'border-emerald-100 bg-emerald-50/60' : 'border-amber-100 bg-amber-50/60'}`}>
              <p className={`text-[12px] font-semibold ${successors.length > 0 ? 'text-emerald-950' : 'text-amber-950'}`}>当前建议动作</p>
              <ol className={`mt-1.5 space-y-1 text-[11px] leading-5 ${successors.length > 0 ? 'text-emerald-950' : 'text-amber-950'}`}>
                {actions.map((action, index) => (
                  <li key={action}>{index + 1}. {action}</li>
                ))}
              </ol>
              {phoneHref && successors.length === 0 ? (
                <p className="mt-2 text-[10px] leading-4 text-amber-800">
                  “公告公开电话”仅来自已核验公开页面。点击拨号不会自动把跟进状态改成“已联系”；实际沟通结果仍由用户明确确认。
                </p>
              ) : null}
            </div>

            <div className="mt-3 rounded-xl bg-slate-50 px-3 py-3">
              <div className="flex items-center gap-2">
                <SearchCheck className="h-4 w-4 text-teal-700" />
                <p className="text-[12px] font-semibold text-slate-800">
                  {successors.length > 0
                    ? `已出现 ${successors.length} 条可能的正式窗口（需核对）`
                    : '当前未发现满足保守关联规则的后续正式商机'}
                </p>
              </div>
              {successors.length > 0 ? (
                <div className="mt-2 space-y-2">
                  {successors.map(({ card, terms, subjectMatch, subject }) => {
                    const deadline = formalDeadlineSummary(card)
                    const basis = subjectMatch
                      ? `项目主题精确一致${subject ? `「${subject}」` : ''}`
                      : `产品重合 ${terms.join('、')}`
                    const formalFollowed = card.followup_status !== 'NEW'
                    const formalBusy = followBusyId === card.opportunity_id
                    const formalReminder = reminderSummary(card)
                    const formalConstraint = formalReminderConstraint(card)
                    return (
                      <div
                        key={card.opportunity_id}
                        className="rounded-lg border border-slate-200 bg-white px-3 py-2.5"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <Link
                              to={`/opportunity/${encodeURIComponent(card.opportunity_id)}`}
                              className="inline-flex items-start gap-1 text-[13px] font-medium leading-5 text-slate-900 hover:text-teal-800"
                            >
                              {card.facts.project_name ?? '正式项目名称未提供'}
                              <ArrowRight className="mt-1 h-3.5 w-3.5 shrink-0 text-teal-700" />
                            </Link>
                            <p className="mt-1 text-[11px] leading-5 text-slate-500">
                              匹配依据：同一采购单位 · {basis}
                              {card.facts.publish_date ? ` · 发布 ${card.facts.publish_date}` : ''}
                            </p>
                            {deadline ? (
                              <p className="mt-1 text-[11px] font-semibold leading-5 text-rose-700">{deadline}</p>
                            ) : null}
                            {formalReminder ? (
                              <p className="mt-1 text-[11px] font-medium text-teal-700">{formalReminder}</p>
                            ) : null}
                          </div>
                        </div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          <Link
                            to={`/opportunity/${encodeURIComponent(card.opportunity_id)}`}
                            className="inline-flex min-h-8 items-center gap-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-[11px] font-medium text-slate-700 hover:bg-slate-50"
                          >
                            核对正式公告
                            <ExternalLink className="h-3 w-3" />
                          </Link>
                          <button
                            type="button"
                            disabled={formalFollowed || Boolean(followBusyId)}
                            onClick={() => void startFollowup(card, 'FORMAL')}
                            className="inline-flex min-h-8 items-center gap-1 rounded-lg border border-teal-200 bg-teal-50 px-2.5 py-1.5 text-[11px] font-medium text-teal-800 hover:bg-teal-100 disabled:cursor-default disabled:border-slate-200 disabled:bg-slate-50 disabled:text-slate-500"
                          >
                            {formalBusy ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : formalFollowed ? (
                              <Check className="h-3 w-3" />
                            ) : (
                              <BookmarkPlus className="h-3 w-3" />
                            )}
                            {formalBusy ? '正在加入…' : formalFollowed ? '正式项目已在跟进' : '加入正式项目跟进'}
                          </button>
                          {formalFollowed && formalConstraint?.canSchedule !== false ? (
                            <button
                              type="button"
                              disabled={Boolean(followBusyId)}
                              onClick={() => setRemindId(card.opportunity_id)}
                              className="inline-flex min-h-8 items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                            >
                              <CalendarClock className="h-3 w-3" />
                              安排正式项目下一步
                            </button>
                          ) : null}
                        </div>
                        {formalFollowed && formalConstraint?.canSchedule === false ? (
                          <p className="mt-2 rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-[10px] leading-4 text-rose-800">
                            最早仍未到的官方节点已临近（{formalConstraint.deadlineHint}），没有安全的未来提醒日；请现在处理，不再延后安排。
                          </p>
                        ) : null}
                        <p className="mt-2 text-[10px] leading-4 text-slate-400">
                          把正式公告加入跟进，只表示你决定跟这条已核验公开商机；不会把候选关联自动升级为“官方确认同一项目”。
                        </p>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <p className="mt-2 text-[11px] leading-5 text-slate-500">
                  这不代表项目取消或没有后续。可能是正式公告尚未发布、当前公开源尚未覆盖，或后续公告产品字段不足且项目主题也无法精确一致。继续监控时不要把“未发现关联”当成业务结论。
                </p>
              )}
            </div>
          </section>
        )
      })}

      <RemindModal
        open={Boolean(remindId)}
        maxDate={reminderConstraint?.canSchedule ? reminderConstraint.maxDate : null}
        deadlineHint={reminderConstraint?.canSchedule ? reminderConstraint.deadlineHint : null}
        onClose={() => setRemindId(null)}
        onConfirm={async (remindAt, nextAction) => {
          if (!remindId) return
          const card = cards.find((item) => item.opportunity_id === remindId)
          if (!card || card.followup_status === 'NEW') return
          const saved = await saveNextAction(card, remindAt, nextAction)
          if (saved) setRemindId(null)
        }}
      />
    </div>
  )
}
