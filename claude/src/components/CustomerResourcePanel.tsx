import { Handshake, PackageSearch, Truck, Wrench } from 'lucide-react';
import type { CustomerContext } from '../types/opportunity';
import { CAPABILITY_TYPE_LABEL, RELATIONSHIP_LABEL, fmtDate } from '../utils/format';
import { SourceTag } from './Badge';
import { cn } from '../utils/cn';

const REL_STRENGTH_DOT: Record<string, string> = {
  STRONG: 'bg-emerald-500',
  MEDIUM: 'bg-amber-500',
  WEAK: 'bg-orange-400',
  NONE: 'bg-slate-300',
};

export function CustomerResourcePanel({ context, compact }: { context: CustomerContext; compact?: boolean }) {
  const rel = context.hospital_relationship;
  const caps = context.matching_product_capabilities;
  const policy = context.partnering_policy;

  return (
    <div className="space-y-3 rounded-lg border border-violet-200 bg-violet-50/50 px-3.5 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <SourceTag tone="customer">我的资源</SourceTag>
        <span className="text-xs text-violet-700">客户确认信息 · 非官方公告</span>
      </div>

      <div>
        {rel ? (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-slate-700">
            <span className="inline-flex items-center gap-1.5">
              <span className={cn('h-2 w-2 rounded-full', REL_STRENGTH_DOT[rel.relationship_strength])} />
              已有医院关系：<b className="font-semibold text-slate-900">{RELATIONSHIP_LABEL[rel.relationship_strength]}</b>
            </span>
            {rel.department && <span>关系科室：{rel.department}</span>}
            {rel.owner && <span>内部负责人：{rel.owner}</span>}
            {!compact && rel.last_confirmed_at && (
              <span className="text-xs text-slate-400">上次确认：{fmtDate(rel.last_confirmed_at)}</span>
            )}
          </div>
        ) : (
          <p className="text-sm text-slate-500">尚未确认院内关系</p>
        )}
      </div>

      {caps.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {caps.map((c, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1.5 rounded-md border border-violet-200 bg-white px-2 py-1 text-xs text-slate-700"
            >
              <PackageSearch className="h-3.5 w-3.5 text-violet-500" />
              <span className="font-medium">{c.subcategory ?? c.category}</span>
              <span className="text-slate-400">·</span>
              <span
                className={cn(
                  c.capability_type === 'DIRECT'
                    ? 'text-emerald-600'
                    : c.capability_type === 'NEEDS_SOURCING'
                      ? 'text-amber-600'
                      : 'text-sky-600',
                )}
              >
                {CAPABILITY_TYPE_LABEL[c.capability_type]}
              </span>
              {c.brands && c.brands.length > 0 && <span className="text-slate-400">（{c.brands.join('、')}）</span>}
            </span>
          ))}
        </div>
      )}

      {policy && !compact && (
        <div className="flex flex-wrap gap-3 border-t border-violet-200/70 pt-2 text-xs text-slate-600">
          <span className="inline-flex items-center gap-1">
            <Truck className="h-3.5 w-3.5 text-violet-500" />
            临时寻找厂家：{policy.can_source_new_vendor ? '可以' : '暂不支持'}
          </span>
          <span className="inline-flex items-center gap-1">
            <Handshake className="h-3.5 w-3.5 text-violet-500" />
            合作渠道商：{policy.can_partner_with_other_distributor ? '可以' : '暂不支持'}
          </span>
          <span className="inline-flex items-center gap-1">
            <Wrench className="h-3.5 w-3.5 text-violet-500" />
            承接租赁项目：{policy.can_support_leasing ? '可以' : '暂不支持'}
          </span>
        </div>
      )}
    </div>
  );
}
