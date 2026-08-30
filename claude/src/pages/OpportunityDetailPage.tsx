import { ArrowLeft, Gauge } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ActionButtons } from "../components/ActionButtons";
import { AIDecisionPanel } from "../components/AIDecisionPanel";
import { CustomerResourcePanel } from "../components/CustomerResourcePanel";
import { EvidenceList } from "../components/EvidenceList";
import { FactsPanel } from "../components/FactsPanel";
import { FollowUpTimeline } from "../components/FollowUpTimeline";
import { PriorityScore } from "../components/PriorityScore";
import { ScriptModal } from "../components/ScriptModal";
import { useToast } from "../components/Toast";
import { todayActionsService } from "../services/MockTodayActionsService";
import type { TodayActionCard } from "../types/today-actions";
import { fallbackText } from "../utils/status";
import { generateOutreachScript } from "../utils/script";

function SectionCard({ children }: { children: React.ReactNode }) {
  return <section className="rounded-2xl border border-slate-100 bg-white p-4 shadow-sm">{children}</section>;
}

export default function OpportunityDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [card, setCard] = useState<TodayActionCard | null | undefined>(undefined);
  const [scriptOpen, setScriptOpen] = useState(false);

  useEffect(() => {
    if (!id) return;
    let mounted = true;
    todayActionsService.getOpportunityById(id).then((result) => {
      if (mounted) setCard(result ?? null);
    });
    return () => {
      mounted = false;
    };
  }, [id]);

  const refresh = async () => {
    if (!id) return;
    const result = await todayActionsService.getOpportunityById(id);
    setCard(result ?? null);
  };

  const handleMark = async (action: string) => {
    if (!id || !card) return;
    await todayActionsService.addFollowUpRecord(id, { actor: "销售·我", action });
    showToast(`已标记为：${action}`);
    await refresh();
  };

  if (card === undefined) {
    return (
      <div className="min-h-screen bg-slate-50 p-4">
        <div className="mx-auto max-w-2xl space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-32 animate-pulse rounded-2xl bg-slate-100" />
          ))}
        </div>
      </div>
    );
  }

  if (card === null) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-slate-50 px-4 text-center">
        <p className="text-slate-500">未找到该商机，可能已被移除或链接有误。</p>
        <Link to="/today" className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white">
          返回今日行动
        </Link>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 pb-10">
      <header className="sticky top-0 z-10 flex items-center gap-2 border-b border-slate-100 bg-white/90 px-4 py-3 backdrop-blur">
        <button
          onClick={() => navigate(-1)}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-slate-500 hover:bg-slate-100"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div className="min-w-0">
          <h1 className="truncate text-[15px] font-bold text-slate-900">商机详情</h1>
          <p className="truncate text-xs text-slate-400">TOP {card.rank} · {card.opportunity_id}</p>
        </div>
      </header>

      <main className="mx-auto max-w-2xl space-y-3.5 px-4 pt-4">
        {/* 标题区 */}
        <SectionCard>
          <div className="space-y-1">
            <h2 className="text-lg font-bold leading-snug text-slate-900">{fallbackText(card.facts.hospital_name)}</h2>
            <p className="text-sm leading-snug text-slate-600">{fallbackText(card.facts.project_name)}</p>
          </div>
        </SectionCard>

        {/* 1. 项目公开信息 */}
        <SectionCard>
          <FactsPanel facts={card.facts} />
        </SectionCard>

        {/* 2. 官方依据 */}
        <SectionCard>
          <EvidenceList sources={card.evidence_source_urls} />
        </SectionCard>

        {/* 3. 我的资源 */}
        <SectionCard>
          <CustomerResourcePanel context={card.customer_context} />
        </SectionCard>

        {/* 4. 商机优先级 */}
        <SectionCard>
          <div className="space-y-3">
            <div className="flex items-center gap-1.5">
              <Gauge className="h-4 w-4 text-slate-400" />
              <h3 className="text-sm font-semibold text-slate-900">商机优先级</h3>
            </div>
            <PriorityScore priority={card.priority} />
            <ul className="space-y-1.5">
              {card.priority.reasons.map((r, i) => (
                <li key={i} className="flex items-start gap-1.5 text-sm text-slate-600">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-slate-400" />
                  {r}
                </li>
              ))}
            </ul>
            <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs leading-relaxed text-slate-400">
              经营优先级用于安排销售资源，不代表中标概率。
            </p>
          </div>
        </SectionCard>

        {/* 5. AI行动建议 */}
        <SectionCard>
          <AIDecisionPanel decision={card.decision} blockReason={card.model_block_reason} />
        </SectionCard>

        {/* 6. 跟进记录 */}
        <SectionCard>
          <FollowUpTimeline records={card.follow_up_records} />
        </SectionCard>

        {/* 操作区 */}
        <SectionCard>
          <ActionButtons onMark={handleMark} onGenerateScript={() => setScriptOpen(true)} />
        </SectionCard>
      </main>

      {scriptOpen && (
        <ScriptModal
          title={`${fallbackText(card.facts.hospital_name)} · 沟通话术`}
          script={generateOutreachScript(card)}
          onClose={() => setScriptOpen(false)}
        />
      )}
    </div>
  );
}
