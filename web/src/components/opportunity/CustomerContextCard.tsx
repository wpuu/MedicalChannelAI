import { Link } from 'react-router-dom'
import type { CustomerContext } from '@/types'
import { FactRow, SectionCard } from '@/components/shared/SectionCard'
import { SourceTag } from '@/components/shared/StageBadge'
import { isVerifiedPublicDemo } from '@/config/demoDataset'
import { isApiMode } from '@/services/apiConfig'
import { formatDate } from '@/utils/format'
import { CAPABILITY_LABEL, RELATIONSHIP_LABEL, yesNo } from '@/utils/labels'

export function CustomerContextCard({ context }: { context: CustomerContext }) {
  const target = context.target_hospital
  const rel = context.hospital_relationship
  const capability = context.matching_product_capabilities[0]
  const policy = context.partnering_policy
  const hasResource = Boolean(
    target ||
      rel ||
      capability ||
      policy.can_find_manufacturer !== null ||
      policy.can_partner_channel !== null ||
      policy.can_handle_lease !== null,
  )

  const subtitle = isApiMode
    ? '客户确认信息 · 非官方公告'
    : isVerifiedPublicDemo
      ? hasResource
        ? '当前浏览器本地填写的客户自有资源 · 与公开采购事实分开保存'
        : '当前尚未填写客户资源 · 不影响查看公开商机'
      : '演示客户资源 · 不代表真实客户信息'

  const sourceLabel = isApiMode
    ? '我的资源 / 客户自有信息'
    : isVerifiedPublicDemo
      ? hasResource
        ? '我的本地资源'
        : '未填写资源'
      : '演示资源'

  return (
    <SectionCard
      title="个性化资源（可选）"
      subtitle={subtitle}
      tone="customer"
      extra={<SourceTag tone="customer">{sourceLabel}</SourceTag>}
    >
      {!isApiMode && isVerifiedPublicDemo ? (
        <div className="mb-3 rounded-xl border border-teal-100 bg-teal-50 px-3 py-2 text-[12px] leading-5 text-teal-900">
          {hasResource
            ? '这些内容来自你在“我的资源”中主动填写，只用于个性化判断；系统不会把它们包装成医院公开事实。目标医院也不会被当成已有医院关系。'
            : '首次体验不需要填写目标医院、医院关系或产品资源。需要更精准关注时，再补充你自己确认的资源。'}
          {!hasResource ? (
            <div className="mt-2">
              <Link
                to="/resources"
                className="inline-flex rounded-lg border border-teal-200 bg-white px-2.5 py-1.5 font-medium text-teal-800 hover:bg-teal-50"
              >
                填写我的资源
              </Link>
            </div>
          ) : null}
        </div>
      ) : !isApiMode ? (
        <div className="mb-3 rounded-xl border border-amber-100 bg-amber-50 px-3 py-2 text-[12px] leading-5 text-amber-900">
          当前为虚构演示客户画像，仅用于验证界面流程。
        </div>
      ) : null}
      <FactRow label="重点关注">
        {target ? (
          <div>
            <p>{target.hospital}</p>
            <p className="text-[12px] text-slate-500">{target.department ? `重点科室：${target.department}` : '全院关注'} · 不代表已有关系</p>
          </div>
        ) : (
          <span className="text-slate-600">未设为目标医院</span>
        )}
      </FactRow>
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
