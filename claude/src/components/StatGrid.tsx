import { Brain, ClipboardList, Flame, Target } from "lucide-react";
import type { TodaySummaryStats } from "../types/today-actions";

export function StatGrid({ stats }: { stats: TodaySummaryStats }) {
  const items = [
    { label: "今日候选", value: stats.total_candidates, icon: ClipboardList, className: "text-slate-600" },
    { label: "匹配商机", value: stats.matched_opportunities, icon: Target, className: "text-sky-600" },
    { label: "今日重点", value: stats.today_focus, icon: Flame, className: "text-rose-600" },
    { label: "AI待分析", value: stats.awaiting_ai, icon: Brain, className: "text-amber-600" },
  ];

  return (
    <div className="grid grid-cols-4 gap-2">
      {items.map(({ label, value, icon: Icon, className }) => (
        <div key={label} className="rounded-xl border border-slate-100 bg-white px-2 py-3 text-center shadow-sm">
          <Icon className={`mx-auto h-4 w-4 ${className}`} />
          <p className="mt-1.5 text-lg font-bold text-slate-900">{value}</p>
          <p className="mt-0.5 text-[11px] leading-tight text-slate-500">{label}</p>
        </div>
      ))}
    </div>
  );
}
