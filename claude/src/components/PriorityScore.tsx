import type { OpportunityPriority } from "../types/today-actions";
import { PRIORITY_TIER_DISPLAY } from "../utils/status";

export function PriorityScore({ priority, compact = false }: { priority: OpportunityPriority; compact?: boolean }) {
  const tierDisplay = PRIORITY_TIER_DISPLAY[priority.tier];

  return (
    <div className={compact ? "flex items-center gap-2" : "flex items-center gap-3"}>
      <div className="flex items-baseline gap-1">
        <span className={compact ? "text-xl font-bold text-slate-900" : "text-3xl font-bold text-slate-900"}>
          {priority.score}
        </span>
        <span className="text-xs text-slate-400">/100</span>
      </div>
      <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${tierDisplay.className}`}>
        {tierDisplay.label}
      </span>
    </div>
  );
}
