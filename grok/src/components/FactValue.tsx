import { EMPTY_FACT } from "@/lib/copy";
import { cn } from "@/utils/cn";

export function FactValue({
  value,
  className,
  emptyLabel = EMPTY_FACT,
}: {
  value: string | string[] | null | undefined;
  className?: string;
  emptyLabel?: string;
}) {
  const empty =
    value == null ||
    value === "" ||
    (Array.isArray(value) && value.length === 0);

  if (empty) {
    return (
      <span className={cn("text-stone-400", className)}>{emptyLabel}</span>
    );
  }

  const text = Array.isArray(value) ? value.join("、") : value;
  return <span className={cn("break-words text-stone-800", className)}>{text}</span>;
}

export function FactRow({
  label,
  value,
  emptyLabel,
}: {
  label: string;
  value: string | string[] | null | undefined;
  emptyLabel?: string;
}) {
  return (
    <div className="grid grid-cols-[88px_minmax(0,1fr)] gap-x-2 gap-y-1 py-1.5">
      <div className="text-[12px] leading-5 text-stone-500">{label}</div>
      <div className="min-w-0 text-[13px] leading-5">
        <FactValue value={value} emptyLabel={emptyLabel} />
      </div>
    </div>
  );
}
