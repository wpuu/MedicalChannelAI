import type { Facts } from '@/types'
import { OfficialText } from '@/components/shared/EmptyValue'
import { PreMarketSignalNotice } from '@/components/shared/PreMarketSignalNotice'
import { FactRow, SectionCard } from '@/components/shared/SectionCard'
import { SourceTag, StageBadge, VerifiedBadge } from '@/components/shared/StageBadge'
import { isVerifiedPublicDemo } from '@/config/demoDataset'
import { isApiMode } from '@/services/apiConfig'
import { formatBudget, formatDate } from '@/utils/format'

function registrationDeadlineDisplay(facts: Facts): string | null {
  if (facts.registration_deadline) return formatDate(facts.registration_deadline)
  if (facts.registration_deadline_date) {
    return `${facts.registration_deadline_date}（未公布具体时间）`
  }
  return null
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

export function FactsCard({ facts }: { facts: Facts }) {
  const subtitle = isApiMode
    ? '官方/已验证事实 · 空值不会自行补全'
    : isVerifiedPublicDemo
      ? '真实公开事实快照 · 空值不会自行补全；客户侧资源另行标注'
      : '虚构演示公开字段 · 用于展示正式版的信息结构与事实边界'
  const sourceLabel = isApiMode
    ? '官方事实'
    : isVerifiedPublicDemo
      ? '真实公开事实'
      : '演示公开字段'
  const contactPhone = facts.official_contact?.phone?.trim() || null
  const contactEmail = facts.official_contact?.email?.trim() || null
  const contactPhoneHref = telHref(contactPhone)
  const contactEmailHref = mailtoHref(contactEmail)
  const isRelativeTestRecruitment =
    facts.notice_type?.includes('测试企业征集公告') === true &&
    !facts.registration_deadline &&
    !facts.registration_deadline_date &&
    !facts.bid_deadline

  return (
    <SectionCard
      title="项目公开信息"
      subtitle={subtitle}
      tone="official"
      extra={
        <div className="flex flex-col items-end gap-1">
          <SourceTag tone="official">{sourceLabel}</SourceTag>
          <VerifiedBadge status={facts.verification_status} />
        </div>
      }
    >
      <PreMarketSignalNotice lifecycleStage={facts.lifecycle_stage} />
      {isRelativeTestRecruitment ? (
        <div className="mb-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-[12px] leading-5 text-amber-900">
          官方原文仅公布“自公告发布之日起7天”的相对报名窗口，没有公布精确截止时刻。系统内部可据此判断行动紧迫度，但不会把推算日期展示成官方截止；实际联系或报名请先向官方确认是否仍开放。
        </div>
      ) : null}
      <FactRow label="项目编号"><OfficialText value={facts.project_code} /></FactRow>
      <FactRow label="项目名称"><OfficialText value={facts.project_name} /></FactRow>
      {isApiMode || isVerifiedPublicDemo || facts.buyer_name ? (
        <FactRow label="采购单位"><OfficialText value={facts.buyer_name ?? null} /></FactRow>
      ) : null}
      <FactRow label="医院"><OfficialText value={facts.hospital} /></FactRow>
      <FactRow label="科室"><OfficialText value={facts.department} /></FactRow>
      <FactRow label="地区"><OfficialText value={facts.region} /></FactRow>
      <FactRow label="项目阶段"><StageBadge stage={facts.lifecycle_stage} /></FactRow>
      <FactRow label="公告类型"><OfficialText value={facts.notice_type ?? null} /></FactRow>
      <FactRow label="发布时间"><OfficialText value={formatDate(facts.publish_date)} /></FactRow>
      <FactRow label={facts.registration_deadline_date && !facts.registration_deadline ? '报名截止日期' : '报名截止'}>
        <OfficialText value={registrationDeadlineDisplay(facts)} />
      </FactRow>
      <FactRow label="投标截止"><OfficialText value={formatDate(facts.bid_deadline)} /></FactRow>
      <FactRow label="预计采购时间"><OfficialText value={formatDate(facts.expected_purchase_date)} /></FactRow>
      <FactRow label="项目预算"><OfficialText value={formatBudget(facts.budget)} /></FactRow>
      <FactRow label="采购方式"><OfficialText value={facts.procurement_method} /></FactRow>
      <FactRow label="采购产品">
        {!facts.products || facts.products.length === 0 ? (
          <OfficialText value={null} />
        ) : (
          <ul className="space-y-1.5">
            {facts.products.map((item) => (
              <li key={`${item.name}-${item.quantity ?? ''}`} className="rounded-lg bg-slate-50 px-2.5 py-2">
                <p className="font-medium">{item.name}</p>
                <p className="text-[12px] text-slate-500">
                  {item.category ?? '暂无公开信息'} · {item.quantity ?? '暂无公开信息'}
                  {item.specification ? ` · ${item.specification}` : ''}
                </p>
              </li>
            ))}
          </ul>
        )}
      </FactRow>
      <FactRow label="公开联系人">
        {!facts.official_contact ? (
          <OfficialText value={null} />
        ) : (
          <div className="space-y-1">
            <p>姓名：<OfficialText value={facts.official_contact.name} /></p>
            <p>职务：<OfficialText value={facts.official_contact.title} /></p>
            <p>
              电话：{contactPhone ? (
                contactPhoneHref ? (
                  <a
                    href={contactPhoneHref}
                    className="font-medium text-teal-700 underline decoration-teal-200 underline-offset-2"
                  >
                    {contactPhone}
                  </a>
                ) : (
                  <span>{contactPhone}</span>
                )
              ) : <OfficialText value={null} />}
            </p>
            <p>
              邮箱：{contactEmail ? (
                contactEmailHref ? (
                  <a
                    href={contactEmailHref}
                    className="font-medium text-teal-700 underline decoration-teal-200 underline-offset-2"
                  >
                    {contactEmail}
                  </a>
                ) : (
                  <span>{contactEmail}</span>
                )
              ) : <OfficialText value={null} />}
            </p>
            {(contactPhoneHref || contactEmailHref) ? (
              <p className="pt-1 text-[11px] leading-5 text-slate-400">
                点击仅打开系统拨号或邮件应用，不会自动把商机标记为“已联系”。
              </p>
            ) : null}
          </div>
        )}
      </FactRow>
    </SectionCard>
  )
}
