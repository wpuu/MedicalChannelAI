import type { CustomerContext } from '@/types'
import { FactRow, SectionCard } from '@/components/shared/SectionCard'
import { SourceTag } from '@/components/shared/StageBadge'
import { formatDate } from '@/utils/format'
import { CAPABILITY_LABEL, RELATIONSHIP_LABEL, yesNo } from '@/utils/labels'

export function CustomerContextCard({ context }: { context: CustomerContext }) {
  const rel = context.hospital_relationship
  const capability = context.matching_product_capabilities[0]
  const policy = context.partnering_policy

  return (
    <SectionCard
      title="我的资源"
      subtitle="客户确认信息 · 非官方公告"
      tone="customer"
      extra={<SourceTag tone="customer">我的资源 / 客户自有信息</SourceTag>}
    >
      <FactRow label="医院关系">
        {rel ? rel.hospital : <span className="text-slate-600">尚未确认院内关系</span>}
      </FactRow>
      <FactRow label="关系科室">{rel?.department ?? '尚未确认院内关系'}</FactRow>
      <FactRow label="关系强度">
        {rel ? RELATIONSHIP_LABEL[rel.relationship_strength] : '尚未确认院内关系'}
      </FactRow>
      <FactRow label="内部负责人">{rel?.owner ?? '未指定'}</FactRow>
      <FactRow label="最近确认">
        {rel?.last_confirmed_at ? formatDate(rel.last_confirmed_at) : '未确认'}
      </FactRow>
      <FactRow label="产品能力">
        {capability ? (
          <div>
            <p>
              {capability.category}
              {capability.subcategory ? ` / ${capability.subcategory}` : ''}
            </p>
            <p className="text-[12px] text-slate-500">
              {CAPABILITY_LABEL[capability.capability_type]}
            </p>
          </div>
        ) : (
          '暂无匹配产品能力'
        )}
      </FactRow>
      <FactRow label="品牌">
        {capability && capability.brands.length > 0 ? capability.brands.join('、') : '未配置品牌'}
      </FactRow>
      <FactRow label="合作厂家能力">{yesNo(policy.can_find_manufacturer)}</FactRow>
      <FactRow label="渠道合作能力">{yesNo(policy.can_partner_channel)}</FactRow>
      <FactRow label="租赁能力">{yesNo(policy.can_handle_lease)}</FactRow>
    </SectionCard>
  )
}
