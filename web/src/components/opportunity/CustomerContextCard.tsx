import type { CustomerContext } from '@/types'
import { FactRow, SectionCard } from '@/components/shared/SectionCard'
import { SourceTag } from '@/components/shared/StageBadge'
import { isApiMode } from '@/services/apiConfig'
import { formatDate } from '@/utils/format'
import { CAPABILITY_LABEL, RELATIONSHIP_LABEL, yesNo } from '@/utils/labels'

export function CustomerContextCard({ context }: { context: CustomerContext }) {
  const rel = context.hospital_relationship
  const capability = context.matching_product_capabilities[0]
  const policy = context.partnering_policy

  return (
    <SectionCard
      title="个性化资源（可选）"
      subtitle={
        isApiMode
          ? '客户确认信息 · 非官方公告'
          : '当前无需录入真实资源 · 以下仅演示录入后系统还能如何进一步判断'
      }
      tone="customer"
      extra={
        <SourceTag tone="customer">
          {isApiMode ? '我的资源 / 客户自有信息' : '可选增强 · 演示资源'}
        </SourceTag>
      }
    >
      {!isApiMode ? (
        <div className="mb-3 rounded-xl border border-teal-100 bg-teal-50 px-3 py-2 text-[12px] leading-5 text-teal-900">
          首次体验不需要填写医院关系、品牌或厂家资源。先看真实公开项目、官方依据和行动建议；确认有价值后，再补充真实资源让排序更精准。
        </div>
      ) : null}
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
      <FactRow label="品牌/方案">
        {capability && capability.brands.length > 0 ? capability.brands.join('、') : '未配置品牌'}
      </FactRow>
      <FactRow label="合作厂家能力">{yesNo(policy.can_find_manufacturer)}</FactRow>
      <FactRow label="渠道合作能力">{yesNo(policy.can_partner_channel)}</FactRow>
      <FactRow label="租赁能力">{yesNo(policy.can_handle_lease)}</FactRow>
    </SectionCard>
  )
}
