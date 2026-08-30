import type { Priority } from '../types/opportunity';
import { PRIORITY_TIER_META } from '../utils/format';
import { cn } from '../utils/cn';

export function PriorityBadge({ priority, size = 'md' }: { priority: Priority; size?: 'sm' | 'md' | 'lg' }) {
  const meta = PRIORITY_TIER_META[priority.tier];
  const sizeClass =
    size === 'lg' ? 'text-2xl px-3 py-1.5' : size === 'sm' ? 'text-sm px-2 py-0.5' : 'text-base px-2.5 py-1';
  return (
    <div className="flex items-center gap-2">
      <span
        className={cn(
          'inline-flex items-center gap-1 rounded-lg border font-bold tabular-nums',
          meta.className,
          sizeClass,
        )}
      >
        {priority.score}
      </span>
      <span
        className={cn(
          'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium',
          meta.className,
        )}
      >
        {meta.label}
      </span>
    </div>
  );
}
