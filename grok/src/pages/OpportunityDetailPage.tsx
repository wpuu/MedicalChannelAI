import { useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ChevronLeft, ExternalLink } from "lucide-react";
import { FactRow } from "@/components/FactValue";
import { ModelStatusBadge } from "@/components/ModelStatusBadge";
import { PriorityScore } from "@/components/PriorityScore";
import { Sheet } from "@/components/Sheets";
import { useToast } from "@/context/ToastContext";
import { useFollowUps, useOpportunity } from "@/hooks/useTodayData";
import {
  CUSTOMER_CONTEXT_BANNER,
  FOLLOW_UP_LABEL,
  MATCH_STATUS_LABEL,
  MODEL_STATUS_HINT,
  PRIORITY_DISCLAIMER,
  RECOMMENDATION_MODE_LABEL,
  RELATIONSHIP_LABEL,
} from "@/lib/copy";
import { compactUrl, formatCnDate, formatCnDateTime } from "@/lib/format";
import { todayActionsService } from "@/services";
import type { CommunicationScript, FollowUpAction } from "@/types/today-actions";
import { cn } from "@/utils/cn";

const ACTIONS: FollowUpAction[] = [
  "contacted",
  "following",
  "not_fit",
  "remind_later",
];

function Section({
  index,
  title,
  caption,
  children,
}: {
  index: string;
  title: string;
  caption?: string;
  children: ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-2xl border border-stone-200/90 bg-white">
      <div className="border-b border-stone-100 px-4 py-3">
        <div className="flex items-baseline gap-2">
          <span className="text-[11px] tabular-nums text-stone-400">{index}</span>
          <h2 className="text-[15px] font-semibold text-stone-900">{title}</h2>
        </div>
        {caption ? (
          <p className="mt-1 text-[12px] leading-relaxed text-stone-500">{caption}</p>
        ) : null}
      </div>
      <div className="px-4 py-3">{children}</div>
    </section>
  );
}

export default function OpportunityDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { toast } = useToast();
  const { card, loading, missing } = useOpportunity(id);
  const { records, actionState } = useFollowUps(id);
  const [note, setNote] = useState("");
  const [script, setScript] = useState<CommunicationScript | null>(null);
  const [scriptLoading, setScriptLoading] = useState(false);

  const addAction = async (action: FollowUpAction, extra?: string) => {
    if (!card) return;
    const remindAt =
      action === "remind_later"
        ? (() => {
            const d = new Date();
            d.setDate(d.getDate() + 1);
            d.setHours(9, 0, 0, 0);
            return d.toISOString();
          })()
        : null;
    const text =
      extra?.trim() ||
      (action === "remind_later" ? "稍后提醒 · 明天 09:00" : FOLLOW_UP_LABEL[action]);
    await todayActionsService.addFollowUp(card.opportunity_id, action, text, remindAt);
    setNote("");
    toast(`已记录：${FOLLOW_UP_LABEL[action]}`);
  };

  const copyScript = async () => {
    if (!script) return;
    const text = [script.opening, ...script.value_points, ...script.questions, script.closing].join(
      "\n",
    );
    try {
      await navigator.clipboard.writeText(text);
      toast("话术已复制");
    } catch {
      toast("当前环境无法复制，请手动选择文本");
    }
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-[720px] px-4 py-10 text-[13px] text-stone-500">
        正在加载商机详情…
      </div>
    );
  }

  if (missing || !card) {
    return (
      <div className="mx-auto max-w-[720px] px-4 py-10">
        <p className="text-[14px] text-stone-700">未找到该商机。</p>
        <Link to="/today" className="mt-3 inline-block text-[13px] text-[#1B4D3E]">
          返回今日行动
        </Link>
      </div>
    );
  }

  const { facts, customer_context: ctx, decision } = card;

  return (
    <div className="min-h-dvh pb-10">
      <header className="sticky top-0 z-30 border-b border-stone-200/80 bg-[#F3F4F2]/92 backdrop-blur">
        <div className="mx-auto flex max-w-[720px] items-center gap-2 px-3 py-2.5 pt-[max(0.6rem,env(safe-area-inset-top))]">
          <button
            type="button"
            onClick={() => navigate("/today")}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white text-stone-700 ring-1 ring-stone-200"
            aria-label="返回今日行动"
          >
            <ChevronLeft className="h-5 w-5" />
          </button>
          <div className="min-w-0">
            <div className="text-[11px] text-stone-500">商机详情 · TOP {card.rank}</div>
            <h1 className="truncate text-[16px] font-semibold text-stone-900">
              {facts.hospital_name ?? "暂无公开信息"}
            </h1>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[720px] space-y-3 px-4 pt-4">
        <Section index="01" title="项目公开信息" caption="官方事实。没有披露的字段显示「暂无公开信息」，不做推测。">
          <FactRow label="医院" value={facts.hospital_name} />
          <FactRow label="采购单位" value={facts.purchaser} />
          <FactRow label="项目名称" value={facts.project_name} />
          <FactRow label="项目阶段" value={facts.project_stage} />
          <FactRow label="预算" value={facts.budget} />
          <FactRow label="截止日期" value={facts.deadline ? formatCnDate(facts.deadline) : null} />
          <FactRow label="预计采购时间" value={facts.expected_purchase_time} />
          <FactRow label="采购产品" value={facts.products} />
          <FactRow label="公开联系人" value={facts.public_contact} />
          <FactRow label="公开电话" value={facts.public_contact_phone} />
          <FactRow
            label="公告日期"
            value={facts.announcement_date ? formatCnDate(facts.announcement_date) : null}
          />
          <FactRow label="地区" value={facts.region} />
          <FactRow label="公告摘要" value={facts.notice_summary} />
        </Section>

        <Section
          index="02"
          title="官方依据"
          caption="仅展示来源入口。演示链接不对应真实公告。"
        >
          {card.evidence_source_urls.length === 0 ? (
            <p className="text-[13px] text-stone-400">暂无公开信息</p>
          ) : (
            <ul className="space-y-2">
              {card.evidence_source_urls.map((url) => (
                <li key={url} className="rounded-xl bg-[#FAFAF8] px-3 py-2.5 ring-1 ring-stone-100">
                  <div className="flex items-center gap-1 text-[12px] font-medium text-[#1B4D3E]">
                    <ExternalLink className="h-3.5 w-3.5" />
                    查看官方依据
                  </div>
                  <p className="mt-1 break-all text-[12px] leading-relaxed text-stone-500">
                    {compactUrl(url)}
                  </p>
                  <p className="mt-0.5 break-all text-[11px] text-stone-400">{url}</p>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section index="03" title="我的资源" caption={CUSTOMER_CONTEXT_BANNER}>
          <div className="rounded-xl border border-[#E8DFD0] bg-[#F7F3EA] p-3">
            <FactRow
              label="医院关系"
              emptyLabel="客户未确认"
              value={
                ctx.hospital_relationship
                  ? `${RELATIONSHIP_LABEL[ctx.relationship_strength]}。${ctx.hospital_relationship}`
                  : RELATIONSHIP_LABEL[ctx.relationship_strength]
              }
            />
            <FactRow label="关系科室" value={ctx.related_department} emptyLabel="客户未确认" />
            <FactRow label="内部负责人" value={ctx.internal_owner} emptyLabel="客户未确认" />
            <FactRow label="产品能力" value={ctx.product_capability} emptyLabel="客户未确认" />
            <FactRow label="品牌" value={ctx.brand} emptyLabel="客户未确认" />
            <FactRow
              label="厂家合作"
              value={ctx.can_find_manufacturer ? "可以找厂家合作（客户确认）" : "当前不需要找厂家"}
            />
            <FactRow
              label="渠道合作"
              value={ctx.can_channel_cooperate ? "可以找渠道合作（客户确认）" : "当前不走渠道合作"}
            />
            <FactRow
              label="供货方式"
              value={ctx.has_direct_product ? "直接有产品，可直接供货" : "需要找厂家/渠道"}
            />
            <FactRow label="补充说明" value={ctx.notes} emptyLabel="客户未确认" />
          </div>
        </Section>

        <Section
          index="04"
          title="商机优先级"
          caption={PRIORITY_DISCLAIMER}
        >
          <PriorityScore score={card.priority.score} label={card.priority.label} compact />
          <p className="mt-3 text-[12px] leading-relaxed text-stone-500">
            {PRIORITY_DISCLAIMER}
          </p>
          <div className="mt-3 grid grid-cols-1 gap-2 text-[13px] sm:grid-cols-2">
            <div className="rounded-xl bg-[#FAFAF8] px-3 py-2">
              <div className="text-[11px] text-stone-500">匹配情况</div>
              <div className="mt-0.5 text-stone-800">{MATCH_STATUS_LABEL[card.match_status]}</div>
            </div>
            <div className="rounded-xl bg-[#FAFAF8] px-3 py-2">
              <div className="text-[11px] text-stone-500">资源安排建议</div>
              <div className="mt-0.5 text-stone-800">
                {RECOMMENDATION_MODE_LABEL[card.recommendation_mode]}
              </div>
            </div>
          </div>
        </Section>

        <Section
          index="05"
          title="AI行动建议"
          caption="只展示建议动作、原因和风险。不展示中标概率。"
        >
          <div className="flex flex-wrap items-center gap-2">
            <ModelStatusBadge status={card.model_decision_status} />
          </div>
          <p className="mt-2 text-[12px] leading-relaxed text-stone-500">
            {MODEL_STATUS_HINT[card.model_decision_status]}
          </p>
          {decision ? (
            <div className="mt-3 space-y-3">
              <div className="rounded-xl bg-[#F4F5F6] p-3">
                <div className="text-[11px] text-stone-500">建议动作</div>
                <p className="mt-1 text-[14px] leading-relaxed text-stone-900">
                  {decision.suggested_action}
                </p>
              </div>
              <div>
                <div className="text-[11px] text-stone-500">原因</div>
                <p className="mt-1 text-[13px] leading-relaxed text-stone-700">{decision.reason}</p>
              </div>
              <div>
                <div className="text-[11px] text-stone-500">风险</div>
                <p className="mt-1 text-[13px] leading-relaxed text-stone-700">{decision.risk}</p>
              </div>
            </div>
          ) : (
            <div className="mt-3 rounded-xl bg-[#F4F5F6] p-3 text-[13px] leading-relaxed text-stone-600">
              {card.model_block_reason ?? "当前不展示AI行动建议。"}
            </div>
          )}
        </Section>

        <Section index="06" title="跟进记录" caption="记录保存在本机，演示结束后可清除浏览器本地数据。">
          <div className="grid grid-cols-2 gap-2">
            {ACTIONS.map((action) => (
              <button
                key={action}
                type="button"
                onClick={() => void addAction(action)}
                className={cn(
                  "h-9 rounded-xl border text-[13px]",
                  actionState.action === action
                    ? "border-[#1B4D3E] bg-[#E8F0EC] text-[#1B4D3E]"
                    : "border-stone-200 text-stone-700",
                )}
              >
                {FOLLOW_UP_LABEL[action]}
              </button>
            ))}
          </div>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={3}
            placeholder="补充跟进说明（可选）"
            className="mt-3 w-full resize-none rounded-xl border border-stone-200 bg-[#FAFAF8] px-3 py-2 text-[13px] leading-relaxed text-stone-800 outline-none focus:border-[#1B4D3E]"
          />
          <button
            type="button"
            onClick={() => void addAction(actionState.action ?? "following", note)}
            className="mt-2 flex h-10 w-full items-center justify-center rounded-xl border border-stone-200 text-[13px] text-stone-700"
          >
            写入跟进说明
          </button>
          <button
            type="button"
            onClick={async () => {
              setScriptLoading(true);
              try {
                setScript(await todayActionsService.generateScript(card.opportunity_id));
              } finally {
                setScriptLoading(false);
              }
            }}
            className="mt-2 flex h-10 w-full items-center justify-center rounded-xl bg-[#1B4D3E] text-[13px] text-white"
          >
            生成沟通话术
          </button>

          <div className="mt-4 space-y-2">
            {records.length === 0 ? (
              <p className="text-[13px] text-stone-400">暂无跟进记录</p>
            ) : (
              records.map((item) => (
                <div key={item.id} className="rounded-xl bg-[#FAFAF8] px-3 py-2.5 ring-1 ring-stone-100">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[12px] font-medium text-stone-800">
                      {FOLLOW_UP_LABEL[item.action]}
                    </span>
                    <span className="text-[11px] text-stone-400">
                      {formatCnDateTime(item.created_at)}
                    </span>
                  </div>
                  <p className="mt-1 text-[13px] leading-relaxed text-stone-600">{item.note}</p>
                  {item.remind_at ? (
                    <p className="mt-1 text-[11px] text-stone-400">
                      提醒时间 {formatCnDateTime(item.remind_at)}
                    </p>
                  ) : null}
                </div>
              ))
            )}
          </div>
        </Section>
      </main>

      <Sheet
        open={Boolean(script) || scriptLoading}
        title="沟通话术"
        caption={script?.disclaimer}
        onClose={() => setScript(null)}
      >
        {scriptLoading || !script ? (
          <p className="text-[13px] text-stone-500">正在生成…</p>
        ) : (
          <div className="space-y-3 text-[13px] leading-relaxed text-stone-800">
            <p>{script.opening}</p>
            <ul className="space-y-1">
              {script.value_points.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <ol className="list-decimal space-y-1 pl-4">
              {script.questions.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ol>
            <p>{script.closing}</p>
            <button
              type="button"
              onClick={() => void copyScript()}
              className="flex h-10 w-full items-center justify-center rounded-xl bg-[#1B4D3E] text-[14px] text-white"
            >
              复制话术
            </button>
          </div>
        )}
      </Sheet>
    </div>
  );
}
