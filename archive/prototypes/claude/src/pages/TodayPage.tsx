import { useEffect, useState, useCallback, type ReactNode } from 'react';
import { AlertTriangle, ListChecks, RefreshCcw, Sparkles, Target, Inbox } from 'lucide-react';
import type { FollowupStatus, NotFitReason, TodayActionsResponse } from '../types/opportunity';
import { todayActionsService } from '../services';
import { CoverageBanner, DemoDataTag } from '../components/CoverageBanner';
import { TodayActionCardView } from '../components/TodayActionCardView';
import { OutreachDrawer } from '../components/OutreachDrawer';
import { useToast } from '../components/ToastProvider';

function formatToday() {
  return new Date().toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    weekday: 'long',
  });
}

function StatCard({ icon, label, value }: { icon: ReactNode; label: string; value: number }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3.5 shadow-sm">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-50 text-slate-500">
        {icon}
      </div>
      <div>
        <p className="text-xs text-slate-500">{label}</p>
        <p className="text-xl font-semibold tabular-nums text-slate-900">{value}</p>
      </div>
    </div>
  );
}

export function TodayPage() {
  const [data, setData] = useState<TodayActionsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshedAt, setRefreshedAt] = useState<Date | null>(null);
  const [outreachTarget, setOutreachTarget] = useState<{ id: string; title: string } | null>(null);
  const { showToast } = useToast();

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    todayActionsService
      .getTodayActions()
      .then((res) => {
        setData(res);
        setRefreshedAt(new Date());
      })
      .catch(() => setError('数据加载失败，请稍后重试'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleUpdateFollowup = async (id: string, status: FollowupStatus, notFitReason?: NotFitReason) => {
    setData((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        cards: prev.cards.map((c) =>
          c.opportunity_id === id
            ? {
                ...c,
                followup: {
                  status,
                  not_fit_reason: notFitReason ?? null,
                  updated_at: new Date().toISOString(),
                  history: [
                    ...c.followup.history,
                    { id: `local-${Date.now()}`, status, not_fit_reason: notFitReason ?? null, at: new Date().toISOString() },
                  ],
                },
              }
            : c,
        ),
      };
    });
    await todayActionsService.updateFollowup(id, { status, not_fit_reason: notFitReason });
    showToast('演示模式：跟进状态已在本地更新', 'success');
  };

  const handleSnooze = (_id: string) => {
    showToast('演示模式：已设置稍后提醒（本地生效）');
  };

  return (
    <div className="mx-auto w-full max-w-[1240px] px-4 py-6 sm:px-6 sm:py-8">
      {/* 顶部 */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-bold text-slate-900 sm:text-2xl">医疗商机助手</h1>
            <DemoDataTag />
          </div>
          <p className="mt-1 text-sm text-slate-500">{formatToday()}</p>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <button
            onClick={load}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
          >
            <RefreshCcw className="h-3.5 w-3.5" />
            刷新
          </button>
          {refreshedAt && (
            <p className="text-xs text-slate-400">最近刷新：{refreshedAt.toLocaleTimeString('zh-CN')}</p>
          )}
        </div>
      </div>

      {data && (
        <div className="mt-4">
          <CoverageBanner text={data.coverage_warning} />
        </div>
      )}

      {/* 概览指标 */}
      {data && (
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard icon={<Inbox className="h-5 w-5" />} label="今日候选" value={data.input_candidate_count} />
          <StatCard icon={<Target className="h-5 w-5" />} label="匹配商机" value={data.matched_count} />
          <StatCard icon={<ListChecks className="h-5 w-5" />} label="今日重点" value={data.card_count} />
          <StatCard icon={<Sparkles className="h-5 w-5" />} label="AI待分析" value={data.model_request_count} />
        </div>
      )}

      <div className="mt-6">
        <h2 className="mb-3 text-sm font-semibold text-slate-500">今天最值得跟进的商机</h2>

        {loading && (
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-64 animate-pulse rounded-2xl border border-slate-200 bg-slate-50" />
            ))}
          </div>
        )}

        {!loading && error && (
          <div className="flex flex-col items-center gap-3 rounded-2xl border border-rose-200 bg-rose-50 px-6 py-12 text-center">
            <AlertTriangle className="h-8 w-8 text-rose-500" />
            <p className="text-sm text-rose-700">{error}</p>
            <button
              onClick={load}
              className="rounded-lg border border-rose-300 bg-white px-3 py-1.5 text-xs font-medium text-rose-700 hover:bg-rose-50"
            >
              重新加载
            </button>
          </div>
        )}

        {!loading && !error && data && data.cards.length === 0 && (
          <div className="flex flex-col items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-6 py-12 text-center">
            <Inbox className="h-8 w-8 text-slate-300" />
            <p className="text-sm text-slate-500">今天暂时没有符合条件的重点商机</p>
          </div>
        )}

        {!loading && !error && data && data.cards.length > 0 && (
          <div className="space-y-4">
            {data.cards.map((card) => (
              <TodayActionCardView
                key={card.opportunity_id}
                card={card}
                onUpdateFollowup={handleUpdateFollowup}
                onOpenOutreach={(id, title) => setOutreachTarget({ id, title })}
                onSnooze={handleSnooze}
              />
            ))}
          </div>
        )}
      </div>

      <OutreachDrawer
        opportunityId={outreachTarget?.id ?? null}
        opportunityTitle={outreachTarget?.title}
        onClose={() => setOutreachTarget(null)}
      />
    </div>
  );
}
