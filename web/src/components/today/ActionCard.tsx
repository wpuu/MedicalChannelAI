import { Building2, Calendar, Mail, Phone, Wallet } from 'lucide-react'
import type { TodayActionCard } from '@/types'
import type { OpportunityFeedback } from '@/services/opportunityFeedbackStore'
import { formatBudget, pickDisplayDate } from '@/utils/format'
import { FOLLOWUP_STATUS_LABEL } from '@/utils/labels'
import { OfficialText } from '@/components/shared/EmptyValue'
import { PreMarketSignalNotice } from '@/components/shared/PreMarketSignalNotice'
import { PriorityBadge, PriorityScore } from '@/components/shared/PriorityBadge'
import { FollowupChip, SourceTag, StageBadge } from '@/components/shared/StageBadge'
import { isVerifiedPublicDemo } from '@/config/demoDataset'
import { isApiMode } from '@/services/apiConfig'
import { ActionButtons } from './ActionButtons'
import { CustomerResourceBlock } from './CustomerResourceBlock'
import { DecisionBlock } from './DecisionBlock'
import { RecommendationFeedback } from './RecommendationFeedback'

interface ActionCardProps {
  card: TodayActionCard
  busy?: boolean
  aiBusy?: boolean
  onDetail: () => void
  onContacted: () => void
  onFollow: () => void
  onNotFit: () => void
  onRemind: () => void
  onOutreach: () => void
  onAnalyze?: () => void
  onFeedbackChanged?: (value: OpportunityFeedback | null) => Promise<void> | void
  analysisUnavailableReason?: string | null
  automationUnavailableReason?: string | null
}

const PRIORITY_DIMENSION_LABELS = [
  ['PRODUCT_EXECUTION_CAPABILITY', '产品执行'],
  ['RELATIONSHIP', '医院关系'],
  ['INTERVENTION_STAGE', '介入时机'],
  ['PROJECT_AMOUNT', '项目金额'],
  ['EXECUTION_FLEXIBILITY', '执行灵活性'],
  ['DEADLINE_URGENCY', '窗口紧迫度'],
  ['PRODUCT_SPECIFICITY', '产品明确度'],
  ['PUBLICATION_FRESHNESS', '信息新鲜度'],
] as const

function priorityDimensionText(card: TodayActionCard): string | null {
  const ranked = PRIORITY_DIMENSION_LABELS
    .map(([key, label]) => ({ label, percent: Number(card.priority.components[key] ?? 0) }))
    .filter((item) => item.percent > 0)
    .sort((left, right) => right.percent - left.percent)
    .slice(0, 3)

  if (ranked.length === 0) return null
  return ranked.map((item) => `${item.label} ${item.percent}%`).join(' · ')
}

function telHref(value: string | null | undefined): string | null {
  const raw = String(value || '').trim()
  if (!raw || /[、,，;；/]/.test(raw)) return null
  const leadingPlus = raw.startsWith('+')
  const digits = raw.replace(/\D/g, '')
  if (digits.length < 5) return null
  return `tel:${leadingPlus ? '+' : ''}${digits}`
}

function mailtoHref(value: string | null | undefined): string | null {
  const email = String(value || '').trim()
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) ? `mailto:${email}` : null
}

export function ActionCard({
  card,
  busy,
  aiBusy,
  onDetail,
  onContacted,
  onFollow,
  onNotFit,
  onRemind,
  onOutreach,
  onAnalyze,
  onFeedbackChanged,
  analysisUnavailableReason,
  automationUnavailableReason,
}: ActionCardProps) {
  const dateInfo = pickDisplayDate(card.facts)
  const budget = formatBudget(card.facts.budget)
  const buyerDisplay = card.facts.hospital ?? card.facts.buyer_name ?? null
  const groundingUnavailable =
    card.model_decision_status === 'BLOCKED_GROUNDING' ||
    card.model_decision_status === 'NOT_ELIGIBLE' ||
    card.evidence_source_urls.length === 0
  const outreachDisabled = groundingUnavailable || Boolean(automationUnavailableReason)
  const outreachDisabledReason = automationUnavailableReason ||
    (groundingUnavailable ? '公开依据不足，暂不安全生成沟通话术' : null)
  const isLateWindow = card.recommendation_mode === 'LATE_WINDOW'
  const isRelativeTestRecruitment =
    card.facts.notice_type?.includes('测试企业征集公告') === true &&
    !card.facts.registration_deadline &&
    !card.facts.registration_deadline_date &&
    !card.facts.bid_deadline
  const priorityDimensions = priorityDimensionText(card)
  const contact = card.facts.official_contact
  const contactIdentity = [contact?.name, contact?.title].filter(
    (value): value is string => Boolean(value),
  )
  const contactPhone = contact?.phone?.trim() || null
  const contactEmail = contact?.email?.trim() || null
  const contactPhoneHref = telHref(contactPhone)
  const contactEmailHref = mailtoHref(contactEmail)
  const hasPublicContact = contactIdentity.length > 0 || Boolean(contactPhone) || Boolean(contactEmail)

  const publicFactLabel = isApiMode
    ? '官方/已验证事实'
    : isVerifiedPublicDemo
      ? '公开信息'
      : '演示公开字段'

  return (
    <article className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-3 py-3 sm:px-4">
        <div className="flex items-center gap-2">
          <span className="rounded-md bg-slate-900 px-2 py-0.5 text-[11px] font-semibold text-white">
            重点 {card.rank}
          </span>
          <PriorityScore score={card.priority.score} scoreScope={card.priority.score_scope} />
          <PriorityBadge score={card.priority.score} scoreScope={card.priority.score_scope} />
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {isLateWindow ? (
            <span className="rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-900">
              报名已结束
            </span>
          ) : null}
          {card.followup_status !== 'NEW' ? (
            <FollowupChip label={FOLLOWUP_STATUS_LABEL[card.followup_status]} />
          ) : null}
        </div>
      </div>

      <div className="grid gap-3 px-3 py-3 sm:px-4 sm:py-4 lg:grid-cols-2">
        <div className="min-w-0 space-y-3">
          <div>
            <div className="mb-1 flex items-center gap-1.5">
              <SourceTag tone="official">{publicFactLabel}</SourceTag>
            </div>
            <div className="flex items-start gap-2">
              <Building2 className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" />
              <div className="min-w-0">
                <p className="text-[15px] font-semibold leading-6 text-slate-900">
                  <OfficialText value={buyerDisplay} />
                </p>
                <p className="mt-0.5 break-words text-[14px] leading-6 text-slate-700">
                  <OfficialText value={card.facts.project_name} />
                </p>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-[12px] text-slate-600">
              <StageBadge stage={card.facts.lifecycle_stage} />
              <span className="inline-flex items-center gap-1">
                <Wallet className="h-3.5 w-3.5 text-slate-400" />
                {budget ? `预算 ${budget}` : <OfficialText value={null} />}
              </span>
              <span className="inline-flex items-center gap-1">
                <Calendar className="h-3.5 w-3.5 text-slate-400" />
                {dateInfo ? `${dateInfo.label} ${dateInfo.value}` : <OfficialText value={null} />}
              </span>
            </div>
            <div className="mt-2">
              <PreMarketSignalNotice
                lifecycleStage={card.facts.lifecycle_stage}
                recommendationMode={card.recommendation_mode}
                compact
              />
            </div>
            {isRelativeTestRecruitment ? (
              <p className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-2 text-[11px] leading-5 text-amber-900">
                官方仅公布“自公告发布之日起7天”的相对报名窗口，未公布精确截止时刻。系统不会把推算日期当作官方截止；联系或报名时请先确认是否仍开放。
              </p>
            ) : null}
            {priorityDimensions ? (
              <p className="mt-2 rounded-lg bg-slate-50 px-2.5 py-2 text-[11px] leading-5 text-slate-600">
                主要匹配维度（完成度）：{priorityDimensions}。维度百分比不是直接加分，也不代表中标概率。
              </p>
            ) : null}
            {hasPublicContact ? (
              <div className="mt-2 rounded-lg border border-slate-100 bg-slate-50/70 px-2.5 py-2 text-[11px] leading-5 text-slate-600">
                <div className="flex items-start gap-1.5">
                  <Phone className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" />
                  <div className="min-w-0">
                    <span>公告公开联系人{contactIdentity.length ? `：${contactIdentity.join(' · ')}` : ''}</span>
                    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
                      {contactPhone ? (
                        contactPhoneHref ? (
                          <a
                            href={contactPhoneHref}
                            className="font-medium text-teal-700 underline decoration-teal-200 underline-offset-2"
                          >
                            电话 {contactPhone}
                          </a>
                        ) : (
                          <span>电话 {contactPhone}</span>
                        )
                      ) : null}
                      {contactEmail ? (
                        contactEmailHref ? (
                          <a
                            href={contactEmailHref}
                            className="inline-flex items-center gap-1 font-medium text-teal-700 underline decoration-teal-200 underline-offset-2"
                          >
                            <Mail className="h-3 w-3" />
                            {contactEmail}
                          </a>
                        ) : (
                          <span>{contactEmail}</span>
                        )
                      ) : null}
                    </div>
                  </div>
                </div>
              </div>
            ) : null}
            {isLateWindow ? (
              <p className="mt-2 rounded-lg bg-amber-50 px-2.5 py-2 text-[11px] leading-5 text-amber-900">
                报名/获取文件时间已过，但投标或响应截止尚未到。建议先确认是否仍有可执行路径。
              </p>
            ) : null}
          </div>
          <CustomerResourceBlock context={card.customer_context} />
        </div>
        <DecisionBlock
          card={card}
          onAnalyze={onAnalyze}
          analyzing={aiBusy}
          analysisUnavailableReason={automationUnavailableReason || analysisUnavailableReason}
          analysisDisabled={Boolean(automationUnavailableReason)}
        />
      </div>

      <RecommendationFeedback
        opportunityId={card.opportunity_id}
        onWorthFollowing={card.followup_status === 'NEW' ? onFollow : undefined}
        onFeedbackChanged={onFeedbackChanged}
      />

      <div className="border-t border-slate-100 px-3 py-3 sm:px-4">
        <ActionButtons
          busy={busy}
          outreachDisabled={outreachDisabled}
          outreachDisabledReason={outreachDisabledReason}
          onDetail={onDetail}
          onContacted={onContacted}
          onFollow={onFollow}
          onNotFit={onNotFit}
          onRemind={onRemind}
          onOutreach={onOutreach}
        />
      </div>
    </article>
  )
}
