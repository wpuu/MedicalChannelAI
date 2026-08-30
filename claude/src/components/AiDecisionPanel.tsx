import { AlertTriangle, Clock3, ShieldAlert, Sparkles, XCircle } from 'lucide-react';
import type { Decision, ModelDecisionStatus } from '../types/opportunity';
import { MODEL_DECISION_STATUS_META } from '../utils/format';
import { cn } from '../utils/cn';

interface Props {
  status: ModelDecisionStatus;
  blockReason?: string | null;
  decision: Decision | null;
  compact?: boolean;
}

export function AiDecisionPanel({ status, blockReason, decision, compact }: Props) {
  const meta = MODEL_DECISION_STATUS_META[status];

  if (status === 'AWAITING_MODEL') {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-500">
        <Clock3 className="h-4 w-4 shrink-0 animate-pulse text-slate-400" />
        <span>{meta.title}</span>
        <span className="ml-auto flex gap-1">
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-300 [animation-delay:-0.2s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-300 [animation-delay:-0.1s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-300" />
        </span>
      </div>
    );
  }

  if (status === 'BLOCKED_GROUNDING') {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-sm text-amber-800">
        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
        <div>
          <p className="font-medium">{meta.title}</p>
          {blockReason && <p className="mt-0.5 text-xs text-amber-700">{blockReason}</p>}
        </div>
      </div>
    );
  }

  if (status === 'MODEL_OUTPUT_REJECTED') {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2.5 text-sm text-rose-800">
        <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-600" />
        <div>
          <p className="font-medium">{meta.title}</p>
          {blockReason && <p className="mt-0.5 text-xs text-rose-700">{blockReason}</p>}
        </div>
      </div>
    );
  }

  if (status === 'NOT_ELIGIBLE') {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-500">
        <span>{meta.title}</span>
      </div>
    );
  }

  // READY
  if (!decision) return null;
  return (
    <div className="space-y-3 rounded-lg border border-teal-200 bg-teal-50/60 px-3.5 py-3">
      <div className="flex items-center gap-1.5 text-xs font-semibold text-teal-700">
        <Sparkles className="h-3.5 w-3.5" />
        AI行动建议
      </div>
      {decision.action && (
        <div>
          <p className="text-xs text-slate-500">建议动作</p>
          <p className="mt-0.5 text-sm font-medium text-slate-800">{decision.action}</p>
        </div>
      )}
      {decision.reasons.length > 0 && (
        <div>
          <p className="text-xs text-slate-500">为什么</p>
          <ul className={cn('mt-1 space-y-1', compact && 'text-sm')}>
            {decision.reasons.map((r, i) => (
              <li key={i} className="flex gap-1.5 text-sm text-slate-700">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-teal-500" />
                <span>{r}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {decision.risks.length > 0 && (
        <div>
          <p className="text-xs text-slate-500">风险</p>
          <ul className="mt-1 space-y-1">
            {decision.risks.map((r, i) => (
              <li key={i} className="flex gap-1.5 text-sm text-amber-700">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>{r}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {decision.requires_human_confirmation && (
        <p className="border-t border-teal-200/70 pt-2 text-xs text-teal-700">建议动作需要销售人工确认后再执行。</p>
      )}
    </div>
  );
}
