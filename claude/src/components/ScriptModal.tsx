import { Check, Copy, MessageSquareText, X } from "lucide-react";
import { useState } from "react";

export function ScriptModal({
  title,
  script,
  onClose,
}: {
  title: string;
  script: string;
  onClose: () => void;
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(script);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 p-0 sm:items-center sm:p-4">
      <div className="max-h-[85vh] w-full max-w-md overflow-y-auto rounded-t-2xl bg-white p-4 shadow-xl sm:rounded-2xl">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2">
            <MessageSquareText className="h-5 w-5 text-sky-600" />
            <h3 className="text-base font-semibold text-slate-900">{title}</h3>
          </div>
          <button onClick={onClose} className="rounded-full p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="mt-3 whitespace-pre-wrap rounded-xl bg-slate-50 p-3.5 text-sm leading-relaxed text-slate-700">
          {script}
        </div>

        <p className="mt-2 text-xs text-slate-400">本话术由本地模板自动生成，供参考，请结合实际情况调整后使用。</p>

        <div className="mt-4 flex gap-2">
          <button
            onClick={handleCopy}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-xl bg-slate-900 py-2.5 text-sm font-medium text-white active:scale-[0.98]"
          >
            {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            {copied ? "已复制" : "复制话术"}
          </button>
          <button
            onClick={onClose}
            className="flex-1 rounded-xl border border-slate-200 py-2.5 text-sm font-medium text-slate-600 active:scale-[0.98]"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}
