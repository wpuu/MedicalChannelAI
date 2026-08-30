import { TODAY_CARDS, TODAY_SUMMARY } from "@/data/today-actions.mock";
import { EMPTY_FACT, FOLLOW_UP_LABEL } from "@/lib/copy";
import { formatCnDate } from "@/lib/format";
import { notifyDataChanged } from "@/services/events";
import type { TodayActionsService } from "@/services/TodayActionsService";
import type {
  CardActionState,
  CommunicationScript,
  FollowUpAction,
  FollowUpRecord,
  TodayActionCard,
  TodayActionsPayload,
  TodayActionsSummary,
} from "@/types/today-actions";

const FOLLOWUP_KEY = "mca.followups.v1";
const ACTION_KEY = "mca.actionState.v1";

function clone<T>(value: T): T {
  return structuredClone(value);
}

function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function writeJson(key: string, value: unknown): void {
  localStorage.setItem(key, JSON.stringify(value));
}

function wait(ms = 60): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function factLine(label: string, value: string | null): string | null {
  if (!value) return null;
  return `${label}${value}`;
}

function buildScript(card: TodayActionCard): CommunicationScript {
  const { facts, customer_context: ctx, decision, model_decision_status } =
    card;
  const usesAi = model_decision_status === "READY" && Boolean(decision);
  const hospital = facts.hospital_name ?? "医院";
  const project = facts.project_name ?? "该采购项目";
  const owner = ctx.internal_owner ?? ctx.related_department ?? "相关老师";
  const greetName = ctx.internal_owner
    ? ctx.internal_owner.replace(/（.*?）/g, "").trim()
    : owner;

  const knownFacts = [
    factLine("医院：", facts.hospital_name),
    factLine("项目：", facts.project_name),
    factLine("阶段：", facts.project_stage),
    factLine("预算：", facts.budget),
    factLine("截止日期：", facts.deadline ? formatCnDate(facts.deadline) : null),
    factLine("预计采购时间：", facts.expected_purchase_time),
    facts.products?.length ? `采购产品：${facts.products.join("、")}` : null,
  ].filter(Boolean) as string[];

  const basedOn = [
    knownFacts.length
      ? `项目公开信息：${knownFacts.join("；")}`
      : "项目公开信息有限，缺失字段按「暂无公开信息」处理",
    `我的资源：${[
      ctx.hospital_relationship,
      ctx.related_department ? `关系科室 ${ctx.related_department}` : null,
      ctx.internal_owner ? `内部负责人 ${ctx.internal_owner}` : null,
      ctx.product_capability,
      ctx.brand ? `品牌 ${ctx.brand}` : null,
    ]
      .filter(Boolean)
      .join("；")}`,
  ];

  if (usesAi && decision) {
    basedOn.push(`AI行动建议：${decision.suggested_action}`);
  }

  const opening = ctx.internal_owner
    ? `${greetName}您好，我是对接${hospital}的同事。看到${project}的公开信息，想跟您确认一下科室这边的评估节奏，也看是否需要我们按公开参数准备对照材料。`
    : `老师您好，我是对接${hospital}的同事。看到${project}已有公开信息，想请教一下目前由哪个科室在看，方便的话想做一次基于公告内容的沟通。`;

  const valuePoints: string[] = [];
  if (ctx.has_direct_product && ctx.product_capability) {
    valuePoints.push(`我的资源：${ctx.product_capability}`);
  } else if (ctx.can_find_manufacturer) {
    valuePoints.push(
      "我的资源：当前没有直接产品，但可以协同厂家/渠道一起评估是否匹配公开需求。",
    );
  }
  if (ctx.relationship_strength === "strong" && ctx.related_department) {
    valuePoints.push(
      `我的资源：与${ctx.related_department}有确认关系，沟通成本相对低，适合先核对事实再决定是否投入方案。`,
    );
  }
  if (facts.deadline) {
    valuePoints.push(
      `公开信息：截止日期为${formatCnDate(facts.deadline)}，适合先确认时间表，而不是先谈结果。`,
    );
  }
  if (facts.budget) {
    valuePoints.push(`公开信息：预算披露为${facts.budget}。只引用公告，不自行加码解读。`);
  }
  if (valuePoints.length === 0) {
    valuePoints.push("当前可说的只有已披露的项目名称与阶段，其余信息按暂无公开信息处理。");
  }

  const questions = [
    facts.public_contact
      ? `公开联系人是${facts.public_contact}，实际评估是否还在使用科室？`
      : "公开信息未列联系人，请问当前是设备科、使用科室还是招标办在牵头？",
    facts.products?.length
      ? `公告中的${facts.products[0]}，科室更关心参数、试剂成本，还是装机与培训？`
      : "目前公开产品信息不完整，能否告知本次采购的核心产品范围？",
    "是否方便基于公告做一次对照，还是需要等正式文件再沟通？",
  ];

  const closing = usesAi && decision
    ? `如果方便，我想按建议推进：${decision.suggested_action} 您看这个时间是否合适？`
    : "如果方便，我想先确认决策科室和下一次可沟通的时间。我不会在信息不全时给结论。";

  const cautions = [
    "只引用公开信息中的医院、项目、预算和日期，没有的字段明确说暂无公开信息。",
    "医院关系、产品能力属于我的资源，需说明是客户确认信息，不是官方公告。",
    "不要承诺结果，不要谈论中标概率。",
  ];
  if (decision?.risk) {
    cautions.push(`已知风险：${decision.risk}`);
  }

  return {
    title: `${hospital} · 沟通话术`,
    disclaimer: usesAi
      ? "本话术基于项目公开信息、我的资源以及AI行动建议生成，仅供内部沟通准备，不代表官方立场，也不代表中标判断。"
      : "当前AI行动建议未就绪。本话术仅基于项目公开信息与我的资源生成，未融合AI建议动作，不代表官方立场。",
    opening,
    value_points: valuePoints,
    questions,
    closing,
    cautions,
    based_on: basedOn,
    uses_ai_decision: usesAi,
  };
}

export class MockTodayActionsService implements TodayActionsService {
  async getTodayPayload(): Promise<TodayActionsPayload> {
    await wait();
    return {
      summary: clone(TODAY_SUMMARY),
      cards: clone(TODAY_CARDS),
    };
  }

  async getTodaySummary(): Promise<TodayActionsSummary> {
    await wait();
    return clone(TODAY_SUMMARY);
  }

  async getTodayCards(): Promise<TodayActionCard[]> {
    await wait();
    return clone(TODAY_CARDS);
  }

  async getOpportunity(id: string): Promise<TodayActionCard | null> {
    await wait();
    const found = TODAY_CARDS.find((c) => c.opportunity_id === id);
    return found ? clone(found) : null;
  }

  async getFollowUps(opportunityId: string): Promise<FollowUpRecord[]> {
    await wait(20);
    const all = readJson<FollowUpRecord[]>(FOLLOWUP_KEY, []);
    return all
      .filter((item) => item.opportunity_id === opportunityId)
      .sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
  }

  async addFollowUp(
    opportunityId: string,
    action: FollowUpAction,
    note: string,
    remindAt?: string | null,
  ): Promise<FollowUpRecord> {
    await wait(20);
    const record: FollowUpRecord = {
      id: `fu-${Date.now()}`,
      opportunity_id: opportunityId,
      action,
      note: note.trim() || FOLLOW_UP_LABEL[action],
      created_at: new Date().toISOString(),
      remind_at: remindAt ?? null,
    };
    const all = readJson<FollowUpRecord[]>(FOLLOWUP_KEY, []);
    all.push(record);
    writeJson(FOLLOWUP_KEY, all);
    await this.setActionState(opportunityId, action, remindAt);
    return record;
  }

  async getActionState(opportunityId: string): Promise<CardActionState> {
    const map = readJson<Record<string, CardActionState>>(ACTION_KEY, {});
    return (
      map[opportunityId] ?? {
        action: null,
        remind_at: null,
        updated_at: null,
      }
    );
  }

  async setActionState(
    opportunityId: string,
    action: FollowUpAction,
    remindAt?: string | null,
  ): Promise<CardActionState> {
    const map = readJson<Record<string, CardActionState>>(ACTION_KEY, {});
    const next: CardActionState = {
      action,
      remind_at: remindAt ?? null,
      updated_at: new Date().toISOString(),
    };
    map[opportunityId] = next;
    writeJson(ACTION_KEY, map);
    notifyDataChanged();
    return next;
  }

  async generateScript(opportunityId: string): Promise<CommunicationScript> {
    await wait(80);
    const card = TODAY_CARDS.find((c) => c.opportunity_id === opportunityId);
    if (!card) {
      return {
        title: "无法生成话术",
        disclaimer: EMPTY_FACT,
        opening: EMPTY_FACT,
        value_points: [],
        questions: [],
        closing: "",
        cautions: [],
        based_on: [],
        uses_ai_decision: false,
      };
    }
    return buildScript(card);
  }
}
