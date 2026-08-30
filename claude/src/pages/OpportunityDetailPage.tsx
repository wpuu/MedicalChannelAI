import { useEffect, useState, useCallback, type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowLeft,
  ExternalLink,
  FileText,
  MessageSquareText,
  ShieldCheck,
} from 'lucide-react';
import type { FollowupStatus, NotFitReason, TodayActionCard } from '../types/opportunity';
import { todayActionsService } from '../services';
import { SourceTag } from '../components/Badge';
import { CustomerResourcePanel } from '../components/CustomerResourcePanel';
import { AiDecisionPanel } from '../components/AiDecisionPanel';
import { PriorityBreakdown } from '../components/PriorityBreakdown';
import { FollowupPanel } from '../components/FollowupPanel';
import { OutreachDrawer } from '../components/OutreachDrawer';
import { useToast } from '../components/ToastProvider';
import {
  EMPTY_TEXT,
  VERIFICATION_STATUS_LABEL,
  COVERAGE_STATUS_LABEL,
  fmtCurrency,
  fmtDate,
  fmtLifecycleStage,
} from '../utils/format';

function FactRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-slate-100 py-2.5 last:border-0 sm:flex-row sm:items-baseline sm:gap-4">
      <span className="w-full shrink-0 text-xs text-slate-400 sm:w-28">{label}</span>
      <span className="text-sm text-slate-800">{value}</span>
    </div>
  );
}

function SectionCard({
  title,
  tag,
  children,
  className = '',
}: {
  title: string;
  tag?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5 ${className}`}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
        {tag}
      </div>
      {children}
    </section>
  );
}

export function OpportunityDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [card, setCard] = useState<TodayActionCard | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [outreachOpen, setOutreachOpen] = useState(false);
  const { showToast } = useToast();

  const load = useCallback(() => {
    if (!id) return;
    setCard(undefined);
    setError(null);
    todayActionsService
      .getOpportunity(id)
      .then((res) => setCard(res))
      .catch(() => setError('数据加载失败，请稍后重试'));
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const handleFollowupChange = async (status: FollowupStatus, notFitReason?: NotFitReason) => {
    if (!id) return;
    setCard((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        followup: {
          status,
          not_fit_reason: notFitReason ?? null,
          updated_at: new Date().toISOString(),
          history: [
            ...prev.followup.history,
            { id: `local-${Date.now()}`, status, not_fit_reason: notFitReason ?? null, at: new Date().toISOString() },
          ],
        },
      };
    });
    await todayActionsService.updateFollowup(id, { status, not_fit_reason: notFitReason });
    showToast('演示模式：跟进状态已在本地更新', 'success');
  };

  if (error) {
    return (
      <div className="mx-auto flex max-w-[1240px] flex-col items-center gap-3 px-4 py-20 text-center">
        <AlertTriangle className="h-8 w-8 text-rose-500" />
        <p className="text-sm text-rose-700">{error}</p>
        <button onClick={load} className="rounded-lg border border-rose-300 bg-white px-3 py-1.5 text-xs font-medium text-rose-700">
          重新加载
        </button>
      </div>
    );
  }

  if (card === undefined) {
    return (
      <div className="mx-auto max-w-[1240px] space-y-4 px-4 py-8 sm:px-6">
        <div className="h-6 w-40 animate-pulse rounded bg-slate-100" />
        <div className="h-48 animate-pulse rounded-2xl bg-slate-50" />
        <div className="h-48 animate-pulse rounded-2xl bg-slate-50" />
      </div>
    );
  }

  if (card === null) {
    return (
      <div className="mx-auto flex max-w-[1240px] flex-col items-center gap-3 px-4 py-20 text-center">
        <p className="text-sm text-slate-500">未找到该商机，可能已被移除或链接有误</p>
        <Link to="/today" className="rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-medium text-white">
          返回今日行动
        </Link>
      </div>
    );
  }

  const { facts } = card;

  return (
    <div className="mx-auto w-full max-w-[1240px] px-4 py-6 sm:px-6 sm:py-8">
      <Link to="/today" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800">
        <ArrowLeft className="h-4 w-4" />
        返回今日行动
      </Link>

      <div className="mt-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold leading-snug text-slate-900 sm:text-xl">{facts.project_name ?? EMPTY_TEXT}</h1>
          <p className="mt-1 text-sm text-slate-500">
            {facts.hospital_name ?? EMPTY_TEXT}
            {facts.department ? ` · ${facts.department}` : ''}
          </p>
        </div>
        <button
          onClick={() => setOutreachOpen(true)}
          className="inline-flex items-center gap-1.5 rounded-lg border border-teal-300 bg-teal-50 px-3.5 py-2 text-sm font-medium text-teal-700 hover:bg-teal-100"
        >
          <MessageSquareText className="h-4 w-4" />
          生成沟通话术
        </button>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          {/* A. 官方事实 */}
          <SectionCard
            title="项目公开信息"
            tag={<SourceTag tone="official">官方公开信息</SourceTag>}
          >
            <FactRow label="项目编号" value={facts.project_code ?? EMPTY_TEXT} />
            <FactRow label="项目名称" value={facts.project_name ?? EMPTY_TEXT} />
            <FactRow label="医院/采购单位" value={facts.hospital_name ?? EMPTY_TEXT} />
            <FactRow label="科室" value={facts.department ?? EMPTY_TEXT} />
            <FactRow label="区域" value={facts.region ?? EMPTY_TEXT} />
            <FactRow label="生命周期阶段" value={fmtLifecycleStage(facts.lifecycle_stage)} />
            <FactRow label="发布日期" value={fmtDate(facts.publish_date)} />
            <FactRow label="报名截止" value={fmtDate(facts.registration_deadline)} />
            <FactRow label="投标截止" value={fmtDate(facts.bid_deadline)} />
            <FactRow label="预计采购时间" value={facts.estimated_procurement_date ?? EMPTY_TEXT} />
            <FactRow label="项目预算" value={fmtCurrency(facts.budget_amount)} />
            <FactRow label="采购方式" value={facts.procurement_method ?? EMPTY_TEXT} />
            <FactRow
              label="采购产品"
              value={
                facts.products.length > 0 ? (
                  <ul className="space-y-0.5">
                    {facts.products.map((p, i) => (
                      <li key={i}>
                        {p.name}
                        {p.spec ? `（${p.spec}）` : ''}
                        {p.quantity ? ` × ${p.quantity}` : ''}
                      </li>
                    ))}
                  </ul>
                ) : (
                  EMPTY_TEXT
                )
              }
            />
            <FactRow
              label="公开联系人"
              value={
                facts.official_contact && (facts.official_contact.name || facts.official_contact.phone || facts.official_contact.org)
                  ? [facts.official_contact.org, facts.official_contact.name, facts.official_contact.phone]
                      .filter(Boolean)
                      .join(' · ')
                  : EMPTY_TEXT
              }
            />
            <div className="mt-3 flex flex-wrap gap-2 pt-1">
              <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-xs text-slate-600">
                核验状态：{VERIFICATION_STATUS_LABEL[facts.verification_status]}
              </span>
              <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-xs text-slate-600">
                数据覆盖：{COVERAGE_STATUS_LABEL[facts.coverage_status]}
              </span>
            </div>
          </SectionCard>

          {/* B. 官方依据 */}
          <SectionCard
            title="官方依据"
            tag={
              <span className="inline-flex items-center gap-1 rounded-full border border-blue-200 bg-blue-50 px-2.5 py-0.5 text-xs font-medium text-blue-700">
                <ShieldCheck className="h-3.5 w-3.5" />
                VERIFIED
              </span>
            }
          >
            {card.evidence_source_urls.length > 0 ? (
              <ul className="space-y-2">
                {card.evidence_source_urls.map((e, i) => (
                  <li key={i}>
                    <a
                      href={e.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm text-blue-700 hover:bg-blue-50"
                    >
                      <FileText className="h-4 w-4 shrink-0 text-blue-500" />
                      <span className="flex-1 truncate">{e.label}</span>
                      <span className="inline-flex shrink-0 items-center gap-1 text-xs text-blue-600">
                        查看官方依据 <ExternalLink className="h-3 w-3" />
                      </span>
                    </a>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-slate-400">{EMPTY_TEXT}</p>
            )}
          </SectionCard>

          {/* E. AI 行动建议 */}
          <SectionCard title="AI行动建议">
            <AiDecisionPanel status={card.model_decision_status} blockReason={card.model_block_reason} decision={card.decision} />
          </SectionCard>

          {/* F. 跟进记录 */}
          <SectionCard title="跟进记录">
            <FollowupPanel followup={card.followup} onChange={handleFollowupChange} />
          </SectionCard>
        </div>

        <div className="space-y-4">
          {/* C. 我的资源 */}
          <SectionCard title="我的资源">
            <CustomerResourcePanel context={card.customer_context} />
          </SectionCard>

          {/* D. 优先级 */}
          <SectionCard title="商机优先级">
            <PriorityBreakdown priority={card.priority} />
          </SectionCard>
        </div>
      </div>

      <OutreachDrawer
        opportunityId={outreachOpen ? card.opportunity_id : null}
        opportunityTitle={facts.project_name ?? undefined}
        onClose={() => setOutreachOpen(false)}
      />
    </div>
  );
}
