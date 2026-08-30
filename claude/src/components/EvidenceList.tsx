import { ExternalLink, FileCheck2 } from "lucide-react";
import type { EvidenceSource } from "../types/today-actions";

export function EvidenceList({ sources }: { sources: EvidenceSource[] }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-1.5">
        <FileCheck2 className="h-4 w-4 text-slate-400" />
        <h3 className="text-sm font-semibold text-slate-900">官方依据</h3>
      </div>

      {sources.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-200 p-3.5 text-sm text-slate-400">暂无公开信息</div>
      ) : (
        <ul className="space-y-2">
          {sources.map((s) => (
            <li key={s.url}>
              <a
                href={s.url}
                target="_blank"
                rel="noreferrer"
                className="flex items-start justify-between gap-2 rounded-xl border border-slate-100 bg-white p-3 text-sm transition hover:border-sky-200 hover:bg-sky-50/50"
              >
                <div className="min-w-0">
                  <p className="truncate font-medium text-slate-800">{s.label}</p>
                  {s.published_at && <p className="mt-0.5 text-xs text-slate-400">发布日期：{s.published_at}</p>}
                </div>
                <ExternalLink className="mt-0.5 h-4 w-4 shrink-0 text-sky-500" />
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
