import { useState } from 'react';
import { CheckCircle2, History } from 'lucide-react';
import type { FollowupState, FollowupStatus, NotFitReason } from '../types/opportunity';
import { FOLLOWUP_STATUS_LABEL, FOLLOWUP_STATUS_ORDER, NOT_FIT_REASON_LABEL, fmtDateTime } from '../utils/format';
import { NotFitReasonDialog } from './NotFitReasonDialog';

interface Props {
  followup: FollowupState;
  onChange: (status: FollowupStatus, notFitReason?: NotFitReason) => void;
}

export function FollowupPanel({ followup, onChange }: Props) {
  const [notFitOpen, setNotFitOpen] = useState(false);
  const [pendingStatus, setPendingStatus] = useState<FollowupStatus | null>(null);

  const handleSelect = (status: FollowupStatus) => {
    if (status === 'NOT_FIT') {
      setPendingStatus(status);
      setNotFitOpen(true);
      return;
    }
    onChange(status);
  };

  return (
    <div>
      <NotFitReasonDialog
        open={notFitOpen}
        onCancel={() => {
          setNotFitOpen(false);
          setPendingStatus(null);
        }}
        onConfirm={(reason) => {
          if (pendingStatus) onChange(pendingStatus, reason);
          setNotFitOpen(false);
          setPendingStatus(null);
        }}
      />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 text-slate-400" />
          <span className="text-sm text-slate-500">当前状态</span>
          <span className="rounded-full bg-slate-900 px-2.5 py-0.5 text-xs font-medium text-white">
            {FOLLOWUP_STATUS_LABEL[followup.status]}
          </span>
          {followup.status === 'NOT_FIT' && followup.not_fit_reason && (
            <span className="text-xs text-rose-600">原因：{NOT_FIT_REASON_LABEL[followup.not_fit_reason]}</span>
          )}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {FOLLOWUP_STATUS_ORDER.map((status) => (
          <button
            key={status}
            onClick={() => handleSelect(status)}
            className={`rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors ${
              followup.status === status
                ? 'border-slate-900 bg-slate-900 text-white'
                : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
            }`}
          >
            {FOLLOWUP_STATUS_LABEL[status]}
          </button>
        ))}
      </div>
      <p className="mt-2 text-xs text-slate-400">演示模式：状态变更仅保存在本地，不代表已同步至服务器。</p>

      <div className="mt-5">
        <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-slate-500">
          <History className="h-3.5 w-3.5" />
          跟进时间线
        </div>
        <ol className="space-y-3 border-l border-slate-200 pl-4">
          {[...followup.history].reverse().map((h) => (
            <li key={h.id} className="relative">
              <span className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full border-2 border-white bg-slate-400" />
              <p className="text-sm font-medium text-slate-800">
                {FOLLOWUP_STATUS_LABEL[h.status]}
                {h.status === 'NOT_FIT' && h.not_fit_reason && (
                  <span className="ml-1.5 text-xs font-normal text-rose-600">
                    · {NOT_FIT_REASON_LABEL[h.not_fit_reason]}
                  </span>
                )}
              </p>
              {h.note && <p className="mt-0.5 text-xs text-slate-500">{h.note}</p>}
              <p className="mt-0.5 text-xs text-slate-400">{fmtDateTime(h.at)}</p>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}
