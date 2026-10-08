import { Link } from 'react-router-dom'
import type { CustomerContext } from '@/types'
import { CAPABILITY_LABEL, RELATIONSHIP_LABEL } from '@/utils/labels'
import { formatDate } from '@/utils/format'
import { SourceTag } from '@/components/shared/StageBadge'
import { isVerifiedPublicDemo } from '@/config/demoDataset'
import { isApiMode } from '@/services/apiConfig'

export function CustomerResourceBlock({ context }: { context: CustomerContext }) {
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
  const canEditResources = isApiMode || isVerifiedPublicDemo
  const missingInputs = [
    !rel ? '医院关系（如有）' : null,
    !capability ? '产品/服务能力' : null,
    policy.can_find_manufacturer === null &&
    policy.can_partner_channel === null &&
    policy.can_handle_lease === null
      ? '执行偏好'
      : null,
  ].filter((value): value is string => Boolean(value))

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
          {target ? (
            <div className="rounded-lg border border-teal-100 bg-white/80 px-2.5 py-2">
              <p>
                重点关注：<span className="font-medium">{target.hospital}</span>
              </p>
              <p className="text-[11px] text-slate-500">
                {target.department ? `重点科室：${target.department} · ` : ''}仅代表你主动关注，不代表已有医院关系
              </p>
            </div>
          ) : null}
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
          ) : target ? (
            <p className="text-[12px] text-slate-500">院内关系：尚未确认；没有真实关系就保持空白。</p>
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
          <p className="pt-1 text-[11px] text-teal-800/70">目标关注用于个性化展示和AI上下文；当前不增加医院关系分。</p>
          {missingInputs.length > 0 ? (
            <div className="mt-2 rounded-lg border border-teal-100 bg-white/80 px-2.5 py-2">
              <p className="text-[11px] leading-5 text-slate-600">
                如有可补：{missingInputs.join('、')}。只填写已确认事实，未知项保持空白。
              </p>
              {canEditResources ? (
                <Link
                  to="/resources"
                  className="mt-2 inline-flex rounded-lg border border-teal-200 bg-white px-2.5 py-1.5 text-[12px] font-medium text-teal-800 hover:bg-teal-50"
                >
                  补充我的资源
                </Link>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : (
        <div>
          <p className="text-[12px] leading-5 text-slate-500">
            不填写也能看公开商机；填写后可优化关注范围和下一步行动。只填写已确认资源，未知项可以留空。
          </p>
          {canEditResources ? (
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
