import { cn } from "@/utils/cn";
import { MODEL_STATUS_LABEL } from "@/lib/copy";
import type { ModelDecisionStatus } from "@/types/today-actions";

const TONE: Record<ModelDecisionStatus, string> = {
  READY: "bg-[#E8F0EC] text-[#1B4D3E] border-[#C9D7D1]",
  AWAITING_MODEL: "bg-stone-100 text-stone-600 border-stone-200",
  BLOCKED_GROUNDING: "bg-[#F4EFE4] text-[#7A5A2B] border-[#E4D6BC]",
  MODEL_OUTPUT_REJECTED: "bg-[#F6EDEA] text-[#7A3E3E] border-[#E6D2CC]",
  NOT_ELIGIBLE: "bg-stone-100 text-stone-500 border-stone-200",
};

export function ModelStatusBadge({
  status,
  className,
}: {
  status: ModelDecisionStatus;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center rounded-full border px-2 py-0.5 text-[11px] leading-4 font-medium",
        TONE[status],
        className,
      )}
    >
      <span className="truncate">{MODEL_STATUS_LABEL[status]}</span>
    </span>
  );
}
