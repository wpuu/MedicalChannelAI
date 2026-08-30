import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { OpportunityCard } from "@/components/OpportunityCard";
import { Logo } from "@/components/Logo";
import { Sheet } from "@/components/Sheets";
import { useToast } from "@/context/ToastContext";
import { useActionStates, useTodayData } from "@/hooks/useTodayData";
import {
  DEMO_BANNER,
  FOLLOW_UP_LABEL,
  PILOT_NOTE,
} from "@/lib/copy";
import { compactUrl, formatTodayHeader } from "@/lib/format";
import { todayActionsService } from "@/services";
import type {
  CommunicationScript,
  FollowUpAction,
  TodayActionCard,
} from "@/types/today-actions";

const STATS = [
  { key: "candidate_count", label: "今日候选" },
  { key: "matched_count", label: "匹配商机" },
  { key: "focus_count", label: "今日重点" },
  { key: "awaiting_ai_count", label: "AI待分析" },
] as const;

function tomorrowNine(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  d.setHours(9, 0, 0, 0);
  return d.toISOString();
}

export default function TodayPage() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { summary, cards, loading } = useTodayData();
  const ids = useMemo(() => cards.map((c) => c.opportunity_id), [cards]);
  const actionMap = useActionStates(ids);

  const [script, setScript] = useState<CommunicationScript | null>(null);
  const [scriptLoading, setScriptLoading] = useState(false);
  const [evidenceCard, setEvidenceCard] = useState<TodayActionCard | null>(null);
  const [remindCard, setRemindCard] = useState<TodayActionCard | null>(null);

  const handleAction = async (card: TodayActionCard, action: FollowUpAction) => {
    if (action === "remind_later") {
      setRemindCard(card);
      return;
    }
    await todayActionsService.addFollowUp(
      card.opportunity_id,
      action,
      FOLLOW_UP_LABEL[action],
    );
    toast(`已记录：${FOLLOW_UP_LABEL[action]}`);
  };

  const confirmRemind = async () => {
    if (!remindCard) return;
    const at = tomorrowNine();
    await todayActionsService.addFollowUp(
      remindCard.opportunity_id,
      "remind_later",
      "稍后提醒 · 明天 09:00",
      at,
    );
    setRemindCard(null);
    toast("已设提醒：明天 09:00");
  };

  const handleScript = async (card: TodayActionCard) => {
    setScriptLoading(true);
    try {
      const result = await todayActionsService.generateScript(card.opportunity_id);
      setScript(result);
    } finally {
      setScriptLoading(false);
    }
  };

  const copyScript = async () => {
    if (!script) return;
    const text = [
      script.title,
      script.disclaimer,
      "",
      "开场",
      script.opening,
      "",
      "可以说的点",
      ...script.value_points.map((x) => `· ${x}`),
      "",
      "建议确认的问题",
      ...script.questions.map((x, i) => `${i + 1}. ${x}`),
      "",
      "收尾",
      script.closing,
      "",
      "注意",
      ...script.cautions.map((x) => `· ${x}`),
    ].join("\n");
    try {
      await navigator.clipboard.writeText(text);
      toast("话术已复制");
    } catch {
      toast("当前环境无法复制，请手动选择文本");
    }
  };

  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-30 border-b border-stone-200/80 bg-[#F3F4F2]/92 backdrop-blur">
        <div className="mx-auto max-w-[720px] px-4 pb-3 pt-[max(0.75rem,env(safe-area-inset-top))]">
          <div className="flex items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-2.5">
              <Logo className="h-8 w-8 shrink-0" />
              <div className="min-w-0">
                <div className="text-[11px] tracking-wide text-stone-500">
                  MedicalChannelAI
                </div>
                <h1 className="truncate text-[18px] font-semibold leading-tight text-stone-900">
                  今日行动
                </h1>
              </div>
            </div>
            <div className="shrink-0 rounded-full border border-[#D7E3DC] bg-[#E8F0EC] px-2.5 py-1 text-[11px] font-medium text-[#1B4D3E]">
              天津 Pilot
            </div>
          </div>
          <p className="mt-2 text-[12px] text-stone-500">{formatTodayHeader()}</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-white px-2 py-0.5 text-[11px] text-stone-600 ring-1 ring-stone-200">
              {DEMO_BANNER}
            </span>
            <span className="min-w-0 text-[11px] leading-relaxed text-stone-500">
              {PILOT_NOTE}
            </span>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[720px] px-4 pb-10 pt-4">
        <section className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {STATS.map((item) => (
            <div
              key={item.key}
              className="rounded-2xl border border-stone-200/90 bg-white px-3 py-3"
            >
              <div className="text-[11px] text-stone-500">{item.label}</div>
              <div className="mt-1 text-[22px] font-semibold tabular-nums leading-none text-stone-900">
                {summary ? summary[item.key] : "–"}
              </div>
            </div>
          ))}
        </section>
        {summary ? (
          <p className="mt-2 text-[11px] text-stone-400">
            {summary.region} · {summary.updated_label} · 最多展示 5 个今日行动
          </p>
        ) : null}

        <section className="mt-4 space-y-3">
          {loading
            ? Array.from({ length: 3 }).map((_, i) => (
                <div
                  key={i}
                  className="h-64 animate-pulse rounded-2xl bg-white/80 ring-1 ring-stone-100"
                />
              ))
            : cards.map((card) => (
                <OpportunityCard
                  key={card.opportunity_id}
                  card={card}
                  actionState={actionMap[card.opportunity_id]}
                  onDetail={() => navigate(`/opportunity/${card.opportunity_id}`)}
                  onAction={(action) => void handleAction(card, action)}
                  onScript={() => void handleScript(card)}
                  onEvidence={() => setEvidenceCard(card)}
                />
              ))}
        </section>

        <p className="mt-8 text-center text-[11px] leading-relaxed text-stone-400">
          MedicalChannelAI · 天津医疗商机助手 Demo
          <br />
          官方事实与我的资源严格分离 · 不展示中标概率
        </p>
      </main>

      <Sheet
        open={Boolean(evidenceCard)}
        title="官方依据"
        caption="演示环境中的依据链接示意，不对应真实医院采购公告。"
        onClose={() => setEvidenceCard(null)}
      >
        {evidenceCard?.evidence_source_urls.length ? (
          <ul className="space-y-2">
            {evidenceCard.evidence_source_urls.map((url) => (
              <li
                key={url}
                className="rounded-xl border border-stone-200 bg-[#FAFAF8] px-3 py-3"
              >
                <div className="text-[12px] font-medium text-stone-800">查看官方依据</div>
                <div className="mt-1 break-all text-[12px] leading-relaxed text-stone-500">
                  {compactUrl(url)}
                </div>
                <div className="mt-1 text-[11px] text-stone-400">{url}</div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[13px] text-stone-500">暂无公开信息</p>
        )}
        <p className="mt-3 text-[12px] leading-relaxed text-stone-400">
          页面不会把链接内容推测成事实。没有披露的字段一律显示「暂无公开信息」。
        </p>
      </Sheet>

      <Sheet
        open={Boolean(remindCard)}
        title="稍后提醒"
        caption="演示环境仅在本地记录提醒，不会发送真实通知。"
        onClose={() => setRemindCard(null)}
      >
        <p className="text-[13px] leading-relaxed text-stone-600">
          将「{remindCard?.facts.hospital_name}」设为明天 09:00 提醒，并写入跟进记录。
        </p>
        <div className="mt-4 grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => setRemindCard(null)}
            className="h-10 rounded-xl border border-stone-200 text-[13px]"
          >
            取消
          </button>
          <button
            type="button"
            onClick={() => void confirmRemind()}
            className="h-10 rounded-xl bg-[#1B4D3E] text-[13px] text-white"
          >
            确认提醒
          </button>
        </div>
      </Sheet>

      <Sheet
        open={Boolean(script) || scriptLoading}
        title="沟通话术"
        caption={script?.disclaimer}
        onClose={() => setScript(null)}
      >
        {scriptLoading || !script ? (
          <p className="text-[13px] text-stone-500">正在根据公开信息与我的资源生成…</p>
        ) : (
          <div className="space-y-4 text-[13px] leading-relaxed">
            <section>
              <h4 className="text-[12px] font-medium text-stone-500">开场</h4>
              <p className="mt-1 text-stone-800">{script.opening}</p>
            </section>
            <section>
              <h4 className="text-[12px] font-medium text-stone-500">可以说的点</h4>
              <ul className="mt-1 space-y-1.5">
                {script.value_points.map((item) => (
                  <li key={item} className="text-stone-800">
                    {item}
                  </li>
                ))}
              </ul>
            </section>
            <section>
              <h4 className="text-[12px] font-medium text-stone-500">建议确认的问题</h4>
              <ol className="mt-1 list-decimal space-y-1.5 pl-4">
                {script.questions.map((item) => (
                  <li key={item} className="text-stone-800">
                    {item}
                  </li>
                ))}
              </ol>
            </section>
            <section>
              <h4 className="text-[12px] font-medium text-stone-500">收尾</h4>
              <p className="mt-1 text-stone-800">{script.closing}</p>
            </section>
            <section className="rounded-xl bg-[#F7F3EA] p-3">
              <h4 className="text-[12px] font-medium text-[#7A5A2B]">注意</h4>
              <ul className="mt-1 space-y-1">
                {script.cautions.map((item) => (
                  <li key={item} className="text-[12px] text-stone-700">
                    {item}
                  </li>
                ))}
              </ul>
            </section>
            <section>
              <h4 className="text-[12px] font-medium text-stone-500">生成依据</h4>
              <ul className="mt-1 space-y-1">
                {script.based_on.map((item) => (
                  <li key={item} className="text-[12px] text-stone-600">
                    {item}
                  </li>
                ))}
              </ul>
            </section>
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
