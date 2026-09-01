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
        ? '我的资源'
        : '可选'
      : '演示资源'

  return (
    <div className="rounded-xl border border-teal-100 bg-teal-50/50 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-[13px] font-semibold text-teal-900">我的资源匹配</p>
        <SourceTag tone="customer">{sourceLabel}</SourceTag>
      </div>
      {hasResource ? (
        <div className="space-y-1.5 text-[13px] leading-6 text-slate-700">
          {rel ? (
            <>
              <p>
                医院关系：
                <span className="font-medium">{RELATIONSHIP_LABEL[rel.relationship_strength]}</span>
              </p>
              {rel.department ? <p>关系科室：{rel.department}</p> : null}
              {rel.owner ? <p>负责人：{rel.owner}</p> : null}
              {rel.last_confirmed_at ? (
                <p className="text-[12px] text-slate-500">
                  最近确认：{formatDate(rel.last_confirmed_at)}
                </p>
              ) : null}
            </>
          ) : null}
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
          ) : null}
          <p className="pt-1 text-[11px] text-teal-800/70">仅用于个性化排序和AI分析。</p>
        </div>
      ) : (
        <div>
          <p className="text-[12px] leading-5 text-slate-500">
            不填写也能看公开商机；填写后可优化排序和AI建议。
          </p>
          {isVerifiedPublicDemo && !isApiMode ? (
            <Link
              to="/resources"
              className="mt-2 inline-flex rounded-lg border border-teal-200 bg-white px-2.5 py-1.5 text-[12px] font-medium text-teal-800 hover:bg-teal-50"
            >
              填写我的资源
            </Link>
          ) : null}
        </div>
      )}
    </div>
  )
}
