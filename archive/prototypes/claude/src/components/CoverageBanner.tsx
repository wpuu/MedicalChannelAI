import { Info } from 'lucide-react';

export function CoverageBanner({ text }: { text: string }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-sky-200 bg-sky-50 px-3.5 py-2.5 text-sm text-sky-800">
      <Info className="mt-0.5 h-4 w-4 shrink-0 text-sky-500" />
      <p>{text}</p>
    </div>
  );
}

export function DemoDataTag() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-fuchsia-200 bg-fuchsia-50 px-2.5 py-0.5 text-xs font-semibold text-fuchsia-700">
      演示数据
    </span>
  );
}
