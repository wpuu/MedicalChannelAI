import { Link } from 'react-router-dom'
import type { CustomerContext } from '@/types'
import { CAPABILITY_LABEL, RELATIONSHIP_LABEL } from '@/utils/labels'
import { formatDate } from '@/utils/format'
import { SourceTag } from '@/components/shared/StageBadge'
import { isVerifiedPublicDemo } from '@/config/demoDataset'
import { isApiMode } from '@/services/apiConfig'

export function CustomerResourceBlock({ context }: { context: CustomerContext }) {
  const rel = context.hospital_relationship
  const capability = context.matching_product_capabilities[0]
  const policy = context.partnering_policy
  const hasResource = Boolean(
    rel ||
      capability ||
      policy.can_find_manufacturer !== null ||
      policy.can_partner_channel !== null ||
      policy.can_handle_lease !== null,
  )

  const sourceLabel = isApiMode
    ? '我的资源'
    : isVerifiedPublicDemo
      ? hasResource
        ? '我的本地资源'
        : '未填写资源'
      : '演示客户资源'

  return (
    <div className="rounded-xl border border-teal-100 bg-teal-50/50 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-[13px] font-semibold text-teal-900">为什么和我有关</p>
        <SourceTag tone="customer">{sourceLabel}</SourceTag>
      </div>
      <div className="space-y-1.5 text-[13px] leading-6 text-slate-700">
        {rel ? (
          <>
            <p>
              已有医院关系：
              <span className="font-medium">{RELATIONSHIP_LABEL[rel.relationship_strength]}</span>
            </p>
            <p>关系科室：{rel.department ?? '未指定科室'}</p>
            <p>内部负责人：{rel.owner ?? '未指定'}</p>
            {rel.last_confirmed_at ? (
              <p className="text-[12px] text-slate-500">
                最近确认：{formatDate(rel.last_confirmed_at)}
              </p>
            ) : null}
          </>
        ) : (
          <p className="text-slate-600">尚未确认院内关系</p>
        )}
        {capability ? (
          <>
            <p>
              匹配产品：
              <span className="font-medium">
                {capability.subcategory ?? capability.category}
              </span>
            </p>
            <p>
              能力：
              <span className="font-medium">{CAPABILITY_LABEL[capability.capability_type]}</span>
            </p>
            {capability.brands.length > 0 ? (
              <p className="text-[12px] text-slate-500">品牌/方案：{capability.brands.join('、')}</p>
            ) : null}
          </>
        ) : (
          <p>暂无匹配产品能力</p>
        )}
      </div>
      {isVerifiedPublicDemo && !isApiMode && !hasResource ? (
        <Link
          to="/resources"
          className="mt-2 inline-flex rounded-lg border border-teal-200 bg-white px-2.5 py-1.5 text-[12px] font-medium text-teal-800 hover:bg-teal-50"
        >
          填写我的资源，让排序更准
        </Link>
      ) : null}
      <p className="mt-2 text-[11px] text-teal-800/80">
        {isApiMode
          ? '客户确认信息 · 非官方公告'
          : isVerifiedPublicDemo
            ? hasResource
              ? '当前浏览器本地填写 · 非医院公开事实'
              : '未录入客户资源时，该部分不参与经营优先级加分'
            : '虚构演示客户画像 · 非真实客户信息'}
      </p>
    </div>
  )
}
