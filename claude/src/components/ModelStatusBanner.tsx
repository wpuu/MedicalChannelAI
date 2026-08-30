import { AlertTriangle, Clock3, ShieldAlert, Sparkles, XCircle } from "lucide-react";
import type { ModelDecisionStatus } from "../types/today-actions";
import { MODEL_STATUS_DISPLAY } from "../utils/status";

const ICONS: Record<ModelDecisionStatus, typeof Sparkles> = {
  READY: Sparkles,
  AWAITING_MODEL: Clock3,
  BLOCKED_GROUNDING: ShieldAlert,
  MODEL_OUTPUT_REJECTED: XCircle,
  NOT_ELIGIBLE: AlertTriangle,
};

export function ModelStatusBanner({
  status,
  blockReason,
}: {
  status: ModelDecisionStatus;
  blockReason?: string | null;
}) {
  const display = MODEL_STATUS_DISPLAY[status];
  const Icon = ICONS[status];

  return (
    <div className={`flex items-start gap-2 rounded-xl px-3 py-2.5 text-sm ${display.className}`}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="min-w-0">
        <p className="font-medium leading-snug">{display.label}</p>
        <p className="mt-0.5 text-xs leading-snug opacity-80">{blockReason || display.description}</p>
      </div>
    </div>
  );
}
