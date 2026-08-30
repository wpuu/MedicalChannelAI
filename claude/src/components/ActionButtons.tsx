import { Bell, MessageSquareText, PhoneCall, ThumbsDown, TrendingUp } from "lucide-react";

const MARK_ACTIONS: { key: string; label: string; icon: typeof PhoneCall; className: string }[] = [
  { key: "已联系", label: "已联系", icon: PhoneCall, className: "text-emerald-700 bg-emerald-50 hover:bg-emerald-100" },
  { key: "继续跟进", label: "继续跟进", icon: TrendingUp, className: "text-sky-700 bg-sky-50 hover:bg-sky-100" },
  { key: "不适合", label: "不适合", icon: ThumbsDown, className: "text-slate-500 bg-slate-100 hover:bg-slate-200" },
  { key: "稍后提醒", label: "稍后提醒", icon: Bell, className: "text-amber-700 bg-amber-50 hover:bg-amber-100" },
];

export function ActionButtons({
  onMark,
  onGenerateScript,
}: {
  onMark: (action: string) => void;
  onGenerateScript: () => void;
}) {
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-4 gap-1.5">
        {MARK_ACTIONS.map(({ key, label, icon: Icon, className }) => (
          <button
            key={key}
            onClick={() => onMark(key)}
            className={`flex flex-col items-center gap-1 rounded-xl px-1 py-2 text-[11px] font-medium transition active:scale-95 ${className}`}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>
      <button
        onClick={onGenerateScript}
        className="flex w-full items-center justify-center gap-1.5 rounded-xl bg-slate-900 py-2.5 text-sm font-medium text-white transition active:scale-[0.98]"
      >
        <MessageSquareText className="h-4 w-4" />
        生成沟通话术
      </button>
    </div>
  );
}
