import type { ReactNode } from 'react';
import { cn } from '../utils/cn';

export function Badge({
  children,
  className,
  icon,
}: {
  children: ReactNode;
  className?: string;
  icon?: ReactNode;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium leading-5 whitespace-nowrap',
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}

export function SourceTag({ tone, children }: { tone: 'official' | 'customer' | 'ai'; children: ReactNode }) {
  const toneClass = {
    official: 'bg-blue-50 text-blue-700 border-blue-200',
    customer: 'bg-violet-50 text-violet-700 border-violet-200',
    ai: 'bg-teal-50 text-teal-700 border-teal-200',
  }[tone];
  return <Badge className={toneClass}>{children}</Badge>;
}
