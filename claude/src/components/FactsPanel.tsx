import { Building2, CalendarClock, ClipboardList, Coins, MapPin, Tag, UserRound } from "lucide-react";
import type { ReactNode } from "react";
import type { ProjectFacts } from "../types/today-actions";
import { fallbackText } from "../utils/status";

export function FactsPanel({ facts }: { facts: ProjectFacts }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <ClipboardList className="h-4 w-4 text-slate-400" />
          <h3 className="text-sm font-semibold text-slate-900">项目公开信息</h3>
        </div>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-500">官方事实</span>
      </div>

      <div className="grid grid-cols-1 gap-2.5 rounded-xl border border-slate-100 bg-white p-3.5">
        <Row icon={<Building2 className="h-4 w-4 text-slate-400" />} label="医院/单位" value={fallbackText(facts.hospital_name)} />
        <Row icon={<ClipboardList className="h-4 w-4 text-slate-400" />} label="项目名称" value={fallbackText(facts.project_name)} />
        <Row icon={<Tag className="h-4 w-4 text-slate-400" />} label="项目阶段" value={fallbackText(facts.project_stage)} />
        <Row icon={<Coins className="h-4 w-4 text-slate-400" />} label="预算" value={fallbackText(facts.budget_amount)} />
        <Row
          icon={<Tag className="h-4 w-4 text-slate-400" />}
          label="采购类别"
          value={
            facts.procurement_category.length ? (
              <div className="flex flex-wrap gap-1.5">
                {facts.procurement_category.map((c) => (
                  <span key={c} className="rounded-full bg-sky-50 px-2 py-0.5 text-xs text-sky-700 ring-1 ring-sky-100">
                    {c}
                  </span>
                ))}
              </div>
            ) : (
              "暂无公开信息"
            )
          }
        />
        <Row
          icon={<CalendarClock className="h-4 w-4 text-slate-400" />}
          label="截止/预计时间"
          value={fallbackText(facts.deadline_or_expected_date)}
        />
        <Row icon={<UserRound className="h-4 w-4 text-slate-400" />} label="公开联系人" value={fallbackText(facts.official_contact)} />
        <Row icon={<MapPin className="h-4 w-4 text-slate-400" />} label="地区" value={facts.region} />
        <Row icon={<CalendarClock className="h-4 w-4 text-slate-400" />} label="公告日期" value={fallbackText(facts.announcement_date)} />
      </div>
    </div>
  );
}

function Row({ icon, label, value }: { icon: ReactNode; label: string; value: ReactNode }) {
  return (
    <div className="flex items-start gap-2 text-sm">
      <div className="mt-0.5 shrink-0">{icon}</div>
      <div className="w-24 shrink-0 text-xs text-slate-500">{label}</div>
      <div className="min-w-0 flex-1 text-slate-800">{value}</div>
    </div>
  );
}
