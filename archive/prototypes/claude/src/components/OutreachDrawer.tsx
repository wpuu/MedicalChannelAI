import { useEffect, useState } from 'react';
import { Copy, Loader2, MessageSquareText, X } from 'lucide-react';
import type { OutreachDraft } from '../types/opportunity';
import { todayActionsService } from '../services';
import { useToast } from './ToastProvider';

interface Props {
  opportunityId: string | null;
  opportunityTitle?: string;
  onClose: () => void;
}

export function OutreachDrawer({ opportunityId, opportunityTitle, onClose }: Props) {
  const [loading, setLoading] = useState(false);
  const [draft, setDraft] = useState<OutreachDraft | null>(null);
  const { showToast } = useToast();

  useEffect(() => {
    if (!opportunityId) {
      setDraft(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setDraft(null);
    todayActionsService.requestOutreachDraft(opportunityId).then((res) => {
      if (!cancelled) {
        setDraft(res);
        setLoading(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [opportunityId]);

  const open = opportunityId !== null;

  const handleCopy = async () => {
    if (!draft) return;
    try {
      await navigator.clipboard.writeText(draft.content);
      showToast('演示模式：话术内容已复制到剪贴板', 'success');
    } catch {
      showToast('复制失败，请手动选中文本复制');
    }
  };

  return (
    <div
      className={`fixed inset-0 z-50 transition-opacity ${open ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'}`}
      aria-hidden={!open}
    >
      <div className="absolute inset-0 bg-slate-900/40" onClick={onClose} />
      <div
        className={`absolute inset-y-0 right-0 flex w-full max-w-md flex-col bg-white shadow-2xl transition-transform duration-300 ${
          open ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <div className="flex items-center gap-2">
            <MessageSquareText className="h-5 w-5 text-teal-600" />
            <h3 className="text-base font-semibold text-slate-900">生成沟通话术</h3>
          </div>
          <button onClick={onClose} className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {opportunityTitle && <p className="mb-3 text-sm text-slate-500">项目：{opportunityTitle}</p>}

          {loading && (
            <div className="flex flex-col items-center justify-center gap-3 py-16 text-slate-400">
              <Loader2 className="h-6 w-6 animate-spin" />
              <p className="text-sm">正在生成演示话术…</p>
            </div>
          )}

          {!loading && draft && (
            <div className="space-y-4">
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-3.5 py-2.5 text-xs text-amber-800">
                {draft.disclaimer}
              </div>
              <div className="whitespace-pre-wrap rounded-lg border border-slate-200 bg-slate-50 px-4 py-3.5 text-sm leading-relaxed text-slate-800">
                {draft.content}
              </div>
              <button
                onClick={handleCopy}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                <Copy className="h-4 w-4" />
                复制话术
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
