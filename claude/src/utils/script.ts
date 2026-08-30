import type { TodayActionCard } from "../types/today-actions";
import { fallbackText } from "./status";

/**
 * 根据商机卡片数据生成一段可直接复制使用的沟通话术（本地模板拼接，非真实AI调用）
 */
export function generateOutreachScript(card: TodayActionCard): string {
  const hospital = fallbackText(card.facts.hospital_name);
  const project = fallbackText(card.facts.project_name);
  const products = card.customer_context.matched_products.length
    ? card.customer_context.matched_products.join("、")
    : "相关产品方案";
  const contact = card.customer_context.internal_contact || "相关负责人";
  const budget = fallbackText(card.facts.budget_amount);

  if (card.model_decision_status !== "READY") {
    return [
      `【提示】该商机AI建议暂未就绪（${card.model_decision_status}），`,
      `以下为基于公开信息的通用初步沟通模板，请结合实际情况人工核实后使用：`,
      "",
      `您好，了解到${hospital}近期有关于「${project}」的相关计划，`,
      `我们在该领域有一定的产品与服务经验，希望有机会做进一步交流，谢谢。`,
    ].join("\n");
  }

  return [
    `您好${contact ? "，" + contact : ""}，`,
    `了解到${hospital}正在推进「${project}」（预算${budget}），`,
    `我们的${products}方案在同类项目中有较好的落地经验，`,
    `想跟您约个时间做一次简短交流，同步一下具体的技术参数和实施方案，`,
    `方便的话可以先发一份产品资料给您参考，您看是否合适？`,
    "",
    `【内部提示】${card.decision.reason ?? ""}`,
  ].join("\n");
}
