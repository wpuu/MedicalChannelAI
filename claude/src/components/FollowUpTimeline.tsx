import { History } from "lucide-react";
import type { FollowUpRecord } from "../types/today-actions";

export function FollowUpTimeline({ records }: { records: FollowUpRecord[] }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-1.5">
        <History className="h-4 w-4 text-slate-400" />
        <h3 className="text-sm font-semibold text-slate-900">跟进记录</h3>
      </div>

      {records.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-200 p-3.5 text-sm text-slate-400">
          暂无跟进记录，操作后将自动生成记录
        </div>
      ) : (
        <ol className="space-y-3 border-l border-slate-200 pl-4">
          {records.map((r) => (
            <li key={r.id} className="relative">
              <span className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full bg-sky-500 ring-4 ring-sky-100" />
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full bg-slate-900 px-2 py-0.5 text-xs font-medium text-white">{r.action}</span>
                <span className="text-xs text-slate-400">{r.timestamp}</span>
                <span className="text-xs text-slate-400">· {r.actor}</span>
              </div>
              {r.note && <p className="mt-1 text-sm text-slate-600">{r.note}</p>}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
