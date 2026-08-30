import { Lightbulb, ShieldAlert, Target } from "lucide-react";
import type { AIDecision } from "../types/today-actions";
import { ModelStatusBanner } from "./ModelStatusBanner";

export function AIDecisionPanel({
  decision,
  blockReason,
  title = "AI行动建议",
}: {
  decision: AIDecision;
  blockReason?: string | null;
  title?: string;
}) {
  const hasContent = decision.status === "READY";

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-1.5">
        <Lightbulb className="h-4 w-4 text-slate-400" />
        <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
      </div>

      <ModelStatusBanner status={decision.status} blockReason={blockReason} />

      {hasContent && (
        <div className="space-y-2.5 rounded-xl bg-slate-50 p-3.5">
          <div className="flex gap-2">
            <Target className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
            <div>
              <p className="text-xs font-medium text-slate-500">建议动作</p>
              <p className="mt-0.5 text-sm leading-relaxed text-slate-800">{decision.recommended_action}</p>
            </div>
          </div>
          <div className="flex gap-2">
            <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-sky-600" />
            <div>
              <p className="text-xs font-medium text-slate-500">原因</p>
              <p className="mt-0.5 text-sm leading-relaxed text-slate-800">{decision.reason}</p>
            </div>
          </div>
          <div className="flex gap-2">
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
            <div>
              <p className="text-xs font-medium text-slate-500">风险</p>
              <p className="mt-0.5 text-sm leading-relaxed text-slate-800">{decision.risk}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
