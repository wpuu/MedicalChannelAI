import { Building2, Handshake, Package, UserRound } from "lucide-react";
import type { ReactNode } from "react";
import type { CustomerContext } from "../types/today-actions";
import { RELATIONSHIP_LEVEL_DISPLAY } from "../utils/status";

export function CustomerResourcePanel({ context }: { context: CustomerContext }) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <Handshake className="h-4 w-4 text-slate-400" />
          <h3 className="text-sm font-semibold text-slate-900">我的资源</h3>
        </div>
        <span className="rounded-full bg-violet-50 px-2 py-0.5 text-[11px] font-medium text-violet-700 ring-1 ring-violet-200">
          客户确认信息 · 非官方公告
        </span>
      </div>

      <div className="grid grid-cols-1 gap-2.5 rounded-xl border border-slate-100 bg-white p-3.5">
        <Row
          icon={<Building2 className="h-4 w-4 text-slate-400" />}
          label="医院关系"
          value={
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                RELATIONSHIP_LEVEL_DISPLAY[context.relationship_level]
              }`}
            >
              {context.relationship_level}
            </span>
          }
        />
        <Row icon={<Building2 className="h-4 w-4 text-slate-400" />} label="关系科室" value={context.related_department || "暂无"} />
        <Row icon={<UserRound className="h-4 w-4 text-slate-400" />} label="内部负责人" value={context.internal_contact || "暂无"} />
        <Row
          icon={<Package className="h-4 w-4 text-slate-400" />}
          label="匹配产品能力"
          value={
            context.matched_products.length ? (
              <div className="flex flex-wrap gap-1.5">
                {context.matched_products.map((p) => (
                  <span key={p} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700">
                    {p}
                  </span>
                ))}
              </div>
            ) : (
              "暂无"
            )
          }
        />
        <Row icon={<Package className="h-4 w-4 text-slate-400" />} label="品牌" value={context.brand || "暂无"} />
        <Row
          icon={<Handshake className="h-4 w-4 text-slate-400" />}
          label="厂家/渠道合作"
          value={context.can_find_vendor_partner ? "可协调厂家/渠道合作资源" : "暂无可协调渠道资源"}
        />
        {context.notes && (
          <div className="mt-1 rounded-lg bg-slate-50 px-3 py-2 text-xs leading-relaxed text-slate-600">
            备注：{context.notes}
          </div>
        )}
      </div>
    </div>
  );
}

function Row({ icon, label, value }: { icon: ReactNode; label: string; value: ReactNode }) {
  return (
    <div className="flex items-start gap-2 text-sm">
      <div className="mt-0.5 shrink-0">{icon}</div>
      <div className="w-20 shrink-0 text-xs text-slate-500">{label}</div>
      <div className="min-w-0 flex-1 text-slate-800">{value}</div>
    </div>
  );
}
