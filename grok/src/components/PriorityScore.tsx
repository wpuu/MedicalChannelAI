import { cn } from "@/utils/cn";
import { PRIORITY_DISCLAIMER_SHORT, getPriorityTone } from "@/lib/copy";

const BAR: Record<string, string> = {
  high: "bg-[#1B4D3E]",
  mid: "bg-[#9A6B2F]",
  low: "bg-[#6B635A]",
  muted: "bg-stone-400",
};

const TEXT: Record<string, string> = {
  high: "text-[#1B4D3E]",
  mid: "text-[#9A6B2F]",
  low: "text-[#57534E]",
  muted: "text-stone-500",
};

export function PriorityScore({
  score,
  label,
  compact = false,
}: {
  score: number;
  label: string;
  compact?: boolean;
}) {
  const tone = getPriorityTone(score);
  return (
    <div className="min-w-0">
      <div className="flex items-end justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[11px] text-stone-500">经营优先级</div>
          <div className="mt-0.5 flex items-baseline gap-2">
            <span className={cn("text-[22px] font-semibold tabular-nums leading-none", TEXT[tone])}>
              {score}
            </span>
            <span className="text-[13px] font-medium text-stone-800">{label}</span>
          </div>
        </div>
        <span className="shrink-0 text-[11px] text-stone-400">{score}/100</span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-stone-200">
        <div
          className={cn("h-full rounded-full", BAR[tone])}
          style={{ width: `${Math.min(100, Math.max(0, score))}%` }}
        />
      </div>
      {!compact ? (
        <p className="mt-2 text-[11px] leading-relaxed text-stone-500">
          {PRIORITY_DISCLAIMER_SHORT}
        </p>
      ) : null}
    </div>
  );
}
