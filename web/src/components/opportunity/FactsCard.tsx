import type { Facts } from '@/types'
import { OfficialText } from '@/components/shared/EmptyValue'
import { FactRow, SectionCard } from '@/components/shared/SectionCard'
import { SourceTag, StageBadge, VerifiedBadge } from '@/components/shared/StageBadge'
import { isVerifiedPublicDemo } from '@/config/demoDataset'
import { isApiMode } from '@/services/apiConfig'
import { formatBudget, formatDate } from '@/utils/format'

export function FactsCard({ facts }: { facts: Facts }) {
  const subtitle = isApiMode
    ? '官方/已验证事实 · 空值不会自行补全'
    : isVerifiedPublicDemo
      ? '真实政府采购公开事实快照 · 空值不会自行补全；客户侧资源另行标注为演示数据'
      : '虚构演示公开字段 · 用于展示正式版的信息结构与事实边界'
  const sourceLabel = isApiMode
    ? '官方事实'
    : isVerifiedPublicDemo
      ? '真实公开事实'
      : '演示公开字段'

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
      <FactRow label="项目编号">
        <OfficialText value={facts.project_code} />
      </FactRow>
      <FactRow label="项目名称">
        <OfficialText value={facts.project_name} />
      </FactRow>
      {isApiMode || isVerifiedPublicDemo || facts.buyer_name ? (
        <FactRow label="采购单位">
          <OfficialText value={facts.buyer_name ?? null} />
        </FactRow>
      ) : null}
      <FactRow label="医院">
        <OfficialText value={facts.hospital} />
      </FactRow>
      <FactRow label="科室">
        <OfficialText value={facts.department} />
      </FactRow>
      <FactRow label="地区">
        <OfficialText value={facts.region} />
      </FactRow>
      <FactRow label="项目阶段">
        <StageBadge stage={facts.lifecycle_stage} />
      </FactRow>
      <FactRow label="公告类型">
        <OfficialText value={facts.notice_type ?? null} />
      </FactRow>
      <FactRow label="发布时间">
        <OfficialText value={formatDate(facts.publish_date)} />
      </FactRow>
      <FactRow label="报名截止">
        <OfficialText value={formatDate(facts.registration_deadline)} />
      </FactRow>
      <FactRow label="投标截止">
        <OfficialText value={formatDate(facts.bid_deadline)} />
      </FactRow>
      <FactRow label="预计采购时间">
        <OfficialText value={formatDate(facts.expected_purchase_date)} />
      </FactRow>
      <FactRow label="项目预算">
        <OfficialText value={formatBudget(facts.budget)} />
      </FactRow>
      <FactRow label="采购方式">
        <OfficialText value={facts.procurement_method} />
      </FactRow>
      <FactRow label="采购产品">
        {!facts.products || facts.products.length === 0 ? (
          <OfficialText value={null} />
        ) : (
          <ul className="space-y-1.5">
            {facts.products.map((item) => (
              <li key={`${item.name}-${item.quantity ?? ''}`} className="rounded-lg bg-slate-50 px-2.5 py-2">
                <p className="font-medium">{item.name}</p>
                <p className="text-[12px] text-slate-500">
                  {item.category ?? '暂无公开信息'}
                  {' · '}
                  {item.quantity ?? '暂无公开信息'}
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
          <div className="space-y-0.5">
            <p>
              姓名：
              <OfficialText value={facts.official_contact.name} />
            </p>
            <p>
              职务：
              <OfficialText value={facts.official_contact.title} />
            </p>
            <p>
              电话：
              <OfficialText value={facts.official_contact.phone} />
            </p>
            <p>
              邮箱：
              <OfficialText value={facts.official_contact.email} />
            </p>
          </div>
        )}
      </FactRow>
    </SectionCard>
  )
}