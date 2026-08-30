import { Stethoscope } from "lucide-react";
import { useEffect, useState } from "react";
import { OpportunityCard } from "../components/OpportunityCard";
import { ScriptModal } from "../components/ScriptModal";
import { StatGrid } from "../components/StatGrid";
import { useToast } from "../components/Toast";
import { todayActionsService } from "../services/MockTodayActionsService";
import type { TodayActionCard, TodaySummaryStats } from "../types/today-actions";
import { generateOutreachScript } from "../utils/script";

export default function TodayPage() {
  const [cards, setCards] = useState<TodayActionCard[]>([]);
  const [stats, setStats] = useState<TodaySummaryStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastActions, setLastActions] = useState<Record<string, string>>({});
  const [scriptState, setScriptState] = useState<{ title: string; script: string } | null>(null);
  const { showToast } = useToast();

  useEffect(() => {
    let mounted = true;
    Promise.all([todayActionsService.getTodayActions(), todayActionsService.getSummaryStats()]).then(
      ([cardList, summary]) => {
        if (!mounted) return;
        setCards(cardList);
        setStats(summary);
        setLoading(false);
      }
    );
    return () => {
      mounted = false;
    };
  }, []);

  const handleMark = async (card: TodayActionCard, action: string) => {
    setLastActions((prev) => ({ ...prev, [card.opportunity_id]: action }));
    await todayActionsService.addFollowUpRecord(card.opportunity_id, {
      actor: "销售·我",
      action,
    });
    showToast(`已标记「${fallbackHospital(card)}」为：${action}`);
  };

  const handleGenerateScript = (card: TodayActionCard) => {
    const script = generateOutreachScript(card);
    setScriptState({ title: `${fallbackHospital(card)} · 沟通话术`, script });
  };

  return (
    <div className="min-h-screen bg-slate-50 pb-10">
      {/* 顶部标题栏 */}
      <header className="sticky top-0 z-10 border-b border-slate-100 bg-white/90 px-4 py-3 backdrop-blur">
        <div className="mx-auto flex max-w-2xl items-center gap-2">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-slate-900">
            <Stethoscope className="h-5 w-5 text-white" />
          </div>
          <div className="min-w-0">
            <h1 className="truncate text-[15px] font-bold text-slate-900">MedicalChannelAI 医疗商机助手</h1>
            <p className="truncate text-xs text-slate-400">今日行动 · 天津 Pilot</p>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-2xl space-y-4 px-4 pt-4">
        {/* 说明条 */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-slate-900 px-2.5 py-1 text-[11px] font-medium text-white">演示数据</span>
          <span className="text-[11px] text-slate-400">当前天津 Pilot，公开数据覆盖持续扩展中</span>
        </div>

        {/* 统计栏 */}
        {stats && <StatGrid stats={stats} />}

        <div>
          <h2 className="mb-2 text-sm font-semibold text-slate-700">今日最值得跟进的商机</h2>

          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-56 animate-pulse rounded-2xl bg-slate-100" />
              ))}
            </div>
          ) : (
            <div className="space-y-3.5">
              {cards.map((card) => (
                <OpportunityCard
                  key={card.opportunity_id}
                  card={card}
                  lastAction={lastActions[card.opportunity_id]}
                  onMark={(action) => handleMark(card, action)}
                  onGenerateScript={() => handleGenerateScript(card)}
                />
              ))}
            </div>
          )}
        </div>

        <p className="pt-2 text-center text-[11px] leading-relaxed text-slate-300">
          经营优先级用于安排销售资源，不代表中标概率。全部数据为演示数据，不构成真实招采信息。
        </p>
      </main>

      {scriptState && (
        <ScriptModal title={scriptState.title} script={scriptState.script} onClose={() => setScriptState(null)} />
      )}
    </div>
  );
}

function fallbackHospital(card: TodayActionCard): string {
  return card.facts.hospital_name || "该商机";
}
