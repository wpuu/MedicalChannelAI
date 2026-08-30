import { ArrowUpRight, Building2, CalendarClock, Coins, ExternalLink, Package } from "lucide-react";
import { useNavigate } from "react-router-dom";
import type { TodayActionCard } from "../types/today-actions";
import { fallbackText, RELATIONSHIP_LEVEL_DISPLAY } from "../utils/status";
import { PriorityScore } from "./PriorityScore";
import { ModelStatusBanner } from "./ModelStatusBanner";
import { ActionButtons } from "./ActionButtons";

export function OpportunityCard({
  card,
  lastAction,
  onMark,
  onGenerateScript,
}: {
  card: TodayActionCard;
  lastAction?: string;
  onMark: (action: string) => void;
  onGenerateScript: () => void;
}) {
  const navigate = useNavigate();
  const evidenceUrl = card.evidence_source_urls[0]?.url;

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-100 bg-white shadow-sm">
      {/* 顶部：排名 + 优先级 */}
      <div className="flex items-center justify-between border-b border-slate-50 bg-gradient-to-r from-slate-50 to-white px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-900 text-xs font-bold text-white">
            {card.rank}
          </span>
          <span className="text-xs font-medium text-slate-400">TOP {card.rank} 商机</span>
        </div>
        <PriorityScore priority={card.priority} compact />
      </div>

      <div className="space-y-3 px-4 py-3.5">
        {/* 医院 + 项目 */}
        <div>
          <div className="flex flex-wrap items-center gap-1.5">
            <Building2 className="h-4 w-4 shrink-0 text-slate-400" />
            <h2 className="text-[15px] font-semibold text-slate-900">{fallbackText(card.facts.hospital_name)}</h2>
            {card.facts.project_stage && (
              <span className="rounded-full bg-sky-50 px-2 py-0.5 text-[11px] font-medium text-sky-700 ring-1 ring-sky-100">
                {card.facts.project_stage}
              </span>
            )}
          </div>
          <p className="mt-1 text-sm leading-snug text-slate-600">{fallbackText(card.facts.project_name)}</p>
        </div>

        {/* 关键信息 */}
        <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 rounded-xl bg-slate-50 px-3 py-2.5 text-xs">
          <div className="flex items-center gap-1.5 text-slate-500">
            <Coins className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate">预算：{fallbackText(card.facts.budget_amount)}</span>
          </div>
          <div className="flex items-center gap-1.5 text-slate-500">
            <CalendarClock className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate">{fallbackText(card.facts.deadline_or_expected_date)}</span>
          </div>
        </div>

        {/* 我的医院关系 + 匹配产品 */}
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          <span className="text-slate-400">我的医院关系</span>
          <span className={`rounded-full px-2 py-0.5 font-medium ${RELATIONSHIP_LEVEL_DISPLAY[card.customer_context.relationship_level]}`}>
            {card.customer_context.relationship_level}
          </span>
          {card.customer_context.matched_products.slice(0, 2).map((p) => (
            <span key={p} className="flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-slate-600">
              <Package className="h-3 w-3" />
              {p}
            </span>
          ))}
        </div>

        {/* AI 状态 / 建议摘要 */}
        <ModelStatusBanner status={card.model_decision_status} blockReason={card.model_block_reason} />
        {card.decision.status === "READY" && (
          <div className="rounded-xl bg-emerald-50/60 px-3 py-2.5 text-xs leading-relaxed text-emerald-900 ring-1 ring-emerald-100">
            <span className="font-semibold">AI行动建议：</span>
            {card.decision.recommended_action}
          </div>
        )}

        {/* 官方依据入口 */}
        {evidenceUrl ? (
          <a
            href={evidenceUrl}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1 text-xs font-medium text-sky-600 hover:underline"
          >
            <ExternalLink className="h-3.5 w-3.5" />
            查看官方依据
          </a>
        ) : (
          <p className="text-xs text-slate-400">暂无公开信息</p>
        )}

        {lastAction && (
          <p className="rounded-lg bg-slate-900/5 px-2.5 py-1.5 text-xs text-slate-500">已标记：{lastAction}</p>
        )}

        {/* 查看详情 */}
        <button
          onClick={() => navigate(`/opportunity/${card.opportunity_id}`)}
          className="flex w-full items-center justify-center gap-1 rounded-xl border border-slate-200 py-2.5 text-sm font-medium text-slate-700 transition hover:border-slate-300 active:scale-[0.98]"
        >
          查看详情
          <ArrowUpRight className="h-4 w-4" />
        </button>

        <ActionButtons onMark={onMark} onGenerateScript={onGenerateScript} />
      </div>
    </div>
  );
}
