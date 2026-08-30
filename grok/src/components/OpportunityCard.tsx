import { CalendarClock, ExternalLink, Hospital, Wallet } from "lucide-react";
import { ModelStatusBadge } from "@/components/ModelStatusBadge";
import { PriorityScore } from "@/components/PriorityScore";
import {
  CUSTOMER_CONTEXT_BANNER,
  FOLLOW_UP_LABEL,
  MATCH_STATUS_LABEL,
  RELATIONSHIP_LABEL,
} from "@/lib/copy";
import { clampText, formatCnDate } from "@/lib/format";
import { cn } from "@/utils/cn";
import type {
  CardActionState,
  FollowUpAction,
  TodayActionCard,
} from "@/types/today-actions";
import { FactValue } from "@/components/FactValue";

const ACTIONS: FollowUpAction[] = [
  "contacted",
  "following",
  "not_fit",
  "remind_later",
];

export function OpportunityCard({
  card,
  actionState,
  onDetail,
  onAction,
  onScript,
  onEvidence,
}: {
  card: TodayActionCard;
  actionState?: CardActionState;
  onDetail: () => void;
  onAction: (action: FollowUpAction) => void;
  onScript: () => void;
  onEvidence: () => void;
}) {
  const { facts, customer_context: ctx, decision } = card;
  const selected = actionState?.action ?? null;
  const isFocus = card.priority.score >= 90;
  const deadlineText = facts.deadline
    ? formatCnDate(facts.deadline)
    : facts.expected_purchase_time;

  return (
    <article
      className={cn(
        "overflow-hidden rounded-2xl border bg-white shadow-[0_1px_2px_rgba(28,25,23,0.04),0_10px_24px_rgba(28,25,23,0.04)]",
        isFocus ? "border-[#C9D7D1]" : "border-stone-200/90",
        selected === "not_fit" ? "opacity-70" : "",
      )}
    >
      <div className={cn("h-1", isFocus ? "bg-[#1B4D3E]" : "bg-stone-200")} />
      <div className="p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex min-w-0 flex-wrap items-center gap-1.5">
            <span className="inline-flex items-center rounded-md bg-[#1B4D3E] px-1.5 py-0.5 text-[11px] font-semibold tracking-wide text-[#F4EFE4]">
              TOP {card.rank}
            </span>
            {selected ? (
              <span className="inline-flex items-center rounded-md bg-stone-100 px-1.5 py-0.5 text-[11px] text-stone-600">
                {FOLLOW_UP_LABEL[selected]}
              </span>
            ) : null}
          </div>
          <ModelStatusBadge status={card.model_decision_status} />
        </div>

        <div className="mt-3 flex items-start gap-2">
          <Hospital className="mt-0.5 h-4 w-4 shrink-0 text-[#1B4D3E]" />
          <div className="min-w-0">
            <h2 className="text-[16px] font-semibold leading-snug text-stone-900">
              {facts.hospital_name ?? "暂无公开信息"}
            </h2>
            <p className="mt-1 text-[14px] leading-relaxed text-stone-700">
              {facts.project_name ?? "暂无公开信息"}
            </p>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1.5 text-[12px] text-stone-600">
          <span className="inline-flex min-w-0 items-center gap-1">
            <span className="text-stone-400">阶段</span>
            <FactValue value={facts.project_stage} className="text-[12px]" />
          </span>
          <span className="inline-flex min-w-0 items-center gap-1">
            <Wallet className="h-3.5 w-3.5 shrink-0 text-stone-400" />
            <FactValue value={facts.budget} className="text-[12px]" />
          </span>
          <span className="inline-flex min-w-0 items-center gap-1">
            <CalendarClock className="h-3.5 w-3.5 shrink-0 text-stone-400" />
            <FactValue
              value={deadlineText}
              className="text-[12px]"
            />
          </span>
        </div>

        <div className="mt-4 rounded-xl border border-stone-100 bg-[#FAFAF8] p-3">
          <PriorityScore
            score={card.priority.score}
            label={card.priority.label}
          />
        </div>

        <div className="mt-3 rounded-xl border border-[#E8DFD0] bg-[#F7F3EA] p-3">
          <div className="text-[11px] font-medium tracking-wide text-[#7A5A2B]">
            {CUSTOMER_CONTEXT_BANNER}
          </div>
          <div className="mt-2 space-y-2">
            <div>
              <div className="text-[11px] text-[#8A7A63]">我的医院关系</div>
              <p className="text-[13px] leading-relaxed text-stone-800">
                {RELATIONSHIP_LABEL[ctx.relationship_strength]}
                {ctx.related_department ? ` · ${ctx.related_department}` : ""}
                {ctx.internal_owner ? ` · ${ctx.internal_owner}` : ""}
              </p>
              <p className="mt-0.5 text-[12px] leading-relaxed text-stone-600">
                {ctx.hospital_relationship ?? "客户未确认医院关系"}
              </p>
            </div>
            <div>
              <div className="text-[11px] text-[#8A7A63]">匹配产品能力</div>
              <p className="text-[13px] leading-relaxed text-stone-800">
                {ctx.has_direct_product ? "可直接供货" : "需找厂家/渠道合作"}
                {ctx.brand ? ` · ${ctx.brand}` : ""}
              </p>
              <p className="mt-0.5 text-[12px] leading-relaxed text-stone-600">
                {ctx.product_capability ?? "客户未确认产品能力"}
              </p>
            </div>
            <div className="text-[11px] text-[#8A7A63]">
              {MATCH_STATUS_LABEL[card.match_status]}
            </div>
          </div>
        </div>

        <div className="mt-3 rounded-xl border border-stone-200 bg-[#F4F5F6] p-3">
          <div className="text-[11px] font-medium tracking-wide text-stone-500">
            AI行动建议
          </div>
          {decision ? (
            <p className="mt-1.5 text-[13px] leading-relaxed text-stone-800">
              {clampText(decision.suggested_action, 88)}
            </p>
          ) : (
            <p className="mt-1.5 text-[13px] leading-relaxed text-stone-600">
              {card.model_block_reason ??
                "当前不展示行动建议，避免把未完成或未通过校验的内容当成结论。"}
            </p>
          )}
        </div>

        <button
          type="button"
          onClick={onEvidence}
          className="mt-3 inline-flex max-w-full items-center gap-1 text-[12px] text-[#1B4D3E]"
        >
          <ExternalLink className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate">
            {card.evidence_source_urls.length > 0
              ? "查看官方依据"
              : "官方依据 · 暂无公开信息"}
          </span>
        </button>

        <div className="mt-4 space-y-2">
          <button
            type="button"
            onClick={onDetail}
            className="flex h-10 w-full items-center justify-center rounded-xl bg-[#1B4D3E] text-[14px] font-medium text-white active:scale-[0.99]"
          >
            查看详情
          </button>
          <div className="grid grid-cols-2 gap-2">
            {ACTIONS.map((action) => (
              <button
                key={action}
                type="button"
                onClick={() => onAction(action)}
                className={cn(
                  "h-9 rounded-xl border text-[13px] active:scale-[0.99]",
                  selected === action
                    ? "border-[#1B4D3E] bg-[#E8F0EC] text-[#1B4D3E]"
                    : "border-stone-200 bg-white text-stone-700",
                )}
              >
                {FOLLOW_UP_LABEL[action]}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={onScript}
            className="flex h-9 w-full items-center justify-center rounded-xl border border-stone-200 bg-white text-[13px] text-stone-700 active:scale-[0.99]"
          >
            生成沟通话术
          </button>
        </div>
      </div>
    </article>
  );
}
