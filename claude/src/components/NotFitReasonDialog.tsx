import { X } from 'lucide-react';
import type { NotFitReason } from '../types/opportunity';
import { NOT_FIT_REASON_LABEL, NOT_FIT_REASON_ORDER } from '../utils/format';

interface Props {
  open: boolean;
  onCancel: () => void;
  onConfirm: (reason: NotFitReason) => void;
}

export function NotFitReasonDialog({ open, onCancel, onConfirm }: Props) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
      <div className="absolute inset-0 bg-slate-900/40" onClick={onCancel} />
      <div className="relative w-full max-w-sm rounded-t-2xl bg-white p-5 shadow-2xl sm:rounded-2xl">
        <div className="mb-3 flex items-center justify-between">
          <h4 className="text-base font-semibold text-slate-900">标记为“不适合”</h4>
          <button onClick={onCancel} className="rounded-md p-1 text-slate-400 hover:bg-slate-100">
            <X className="h-5 w-5" />
          </button>
        </div>
        <p className="mb-3 text-sm text-slate-500">请选择主要原因，帮助团队优化后续匹配：</p>
        <div className="grid grid-cols-2 gap-2">
          {NOT_FIT_REASON_ORDER.map((reason) => (
            <button
              key={reason}
              onClick={() => onConfirm(reason)}
              className="rounded-lg border border-slate-200 px-3 py-2 text-left text-sm text-slate-700 hover:border-rose-300 hover:bg-rose-50"
            >
              {NOT_FIT_REASON_LABEL[reason]}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
