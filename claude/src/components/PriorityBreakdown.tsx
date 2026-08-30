import type { Priority } from '../types/opportunity';
import { PRIORITY_TIER_META } from '../utils/format';

export function PriorityBreakdown({ priority }: { priority: Priority }) {
  const meta = PRIORITY_TIER_META[priority.tier];
  return (
    <div>
      <div className="flex items-end gap-3">
        <span className="text-4xl font-bold tabular-nums text-slate-900">{priority.score}</span>
        <span className={`mb-1 inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${meta.className}`}>
          {meta.label}
        </span>
      </div>
      <p className="mt-1 text-xs text-slate-500">经营优先级，用于安排销售资源，不代表中标概率。</p>

      <div className="mt-4 space-y-3">
        {priority.components.map((c) => (
          <div key={c.key}>
            <div className="mb-1 flex items-center justify-between text-xs text-slate-600">
              <span>{c.label}</span>
              <span className="tabular-nums font-medium text-slate-800">{c.score}</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
              <div className={`h-full rounded-full ${meta.barClassName}`} style={{ width: `${c.score}%` }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
