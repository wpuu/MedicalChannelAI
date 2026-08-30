import type {
  TodayActionCard,
  TodayActionsSummary,
} from "@/types/today-actions";

export const TODAY_SUMMARY: TodayActionsSummary = {
  candidate_count: 5,
  matched_count: 3,
  focus_count: 2,
  awaiting_ai_count: 1,
  region: "天津",
  updated_label: "今日 07:30 更新",
};

export const TODAY_CARDS: TodayActionCard[] = [
  {
    rank: 1,
    opportunity_id: "tj-2026-001",
    facts: {
      hospital_name: "天津某三甲医院",
      purchaser: "天津某三甲医院设备科",
      project_name: "化学发光免疫分析系统及配套试剂采购项目",
      project_stage: "公开招标（已发公告）",
      budget: "人民币 860 万元",
      deadline: "2026-04-18",
      expected_purchase_time: "2026年二季度",
      products: [
        "全自动化学发光免疫分析仪",
        "配套检测试剂",
        "校准品质控品",
      ],
      public_contact: "设备科 张工",
      public_contact_phone: "022-0000-1001（公开）",
      announcement_date: "2026-03-12",
      region: "天津",
      notice_summary:
        "拟采购化学发光免疫分析系统及配套试剂，用于检验科常规免疫检测项目扩容。公告载明需提供装机、培训及质保。",
    },
    evidence_source_urls: [
      "https://demo.medicalchannel.ai/sources/tj/notice/2026-03-12-chemilum",
      "https://demo.medicalchannel.ai/sources/tj/params/2026-03-12-chemilum",
    ],
    customer_context: {
      hospital_relationship:
        "与该院检验科保持稳定沟通，近 12 个月有过三次科室拜访记录。",
      related_department: "检验科",
      internal_owner: "李主任（客户确认）",
      product_capability:
        "自有化学发光仪器及试剂产品线，可覆盖激素、感染、肿瘤标志物常规项目，可直接供货。",
      brand: "自有品牌",
      can_find_manufacturer: false,
      can_channel_cooperate: false,
      relationship_strength: "strong",
      has_direct_product: true,
      notes: "李主任关注装机周期和试剂成本，不喜欢只谈设备不谈试剂闭环。",
    },
    priority: { score: 94, label: "立即关注" },
    match_status: "STRONG_RELATION_DIRECT_PRODUCT",
    recommendation_mode: "FOLLOW_NOW",
    model_decision_status: "READY",
    model_block_reason: null,
    decision: {
      suggested_action:
        "今日内电话联系检验科李主任，确认是否已有平台倾向，并预约下周参数对照与试剂成本测算。",
      reason:
        "公开招标已发布且截止日期临近；你在该院检验科有确认关系，同时具备可直接供货的化学发光产品，跟进窗口明确。",
      risk:
        "公告未写明试剂开放/封闭要求，也未说明是否绑定原装试剂。先核对比参数，避免按错误假设做方案。",
    },
  },
  {
    rank: 2,
    opportunity_id: "tj-2026-002",
    facts: {
      hospital_name: "天津某中心医院",
      purchaser: "天津某中心医院",
      project_name: "POCT 床旁快速检测设备及试剂集中采购",
      project_stage: "需求调研 / 意向采购",
      budget: "人民币 320 万元",
      deadline: null,
      expected_purchase_time: "2026年二季度",
      products: ["POCT 分析仪", "心肌标志物试剂", "感染标志物试剂"],
      public_contact: null,
      public_contact_phone: null,
      announcement_date: "2026-03-08",
      region: "天津",
      notice_summary:
        "医院公开意向信息显示，拟为急诊、心内及相关病区补充床旁快速检测能力。未公布具体品牌和联系人。",
    },
    evidence_source_urls: [
      "https://demo.medicalchannel.ai/sources/tj/intent/2026-03-08-poct",
    ],
    customer_context: {
      hospital_relationship:
        "曾拜访过设备科，留下名片和资料，尚无稳定内部对接人。",
      related_department: "设备科（弱接点）",
      internal_owner: null,
      product_capability:
        "已有 POCT 产品，可覆盖心肌标志物与感染标志物两项，可直接供货。",
      brand: "自有品牌",
      can_find_manufacturer: false,
      can_channel_cooperate: true,
      relationship_strength: "weak",
      has_direct_product: true,
      notes: "需要尽快从设备科接点转到急诊或检验科使用科室。",
    },
    priority: { score: 82, label: "重点跟进" },
    match_status: "WEAK_RELATION_DIRECT_PRODUCT",
    recommendation_mode: "FOLLOW_NOW",
    model_decision_status: "READY",
    model_block_reason: null,
    decision: {
      suggested_action:
        "本周通过已有设备科接点，约一次急诊+检验科联合沟通，确认 POCT 使用场景、现有品牌和决策科室。",
      reason:
        "项目仍在需求调研，入场成本相对较低；你有现成 POCT 产品，但医院关系弱，应先补齐使用科室关系再推方案。",
      risk:
        "公开信息未披露预算拆分和科室主导权，存在设备科与临床意见不一致的可能。不要在未确认使用场景前承诺配置。",
    },
  },
  {
    rank: 3,
    opportunity_id: "tj-2026-003",
    facts: {
      hospital_name: "天津某专科医院",
      purchaser: "天津某专科医院",
      project_name: "智能采血管理系统及终端设备建设项目",
      project_stage: "政府采购意向公开",
      budget: "人民币 180 万元",
      deadline: null,
      expected_purchase_time: "2026年三季度",
      products: ["智能采血管准备系统", "排队叫号终端", "标本流转模块"],
      public_contact: "招标办（公开栏仅列部门）",
      public_contact_phone: null,
      announcement_date: "2026-03-15",
      region: "天津",
      notice_summary:
        "意向公开显示医院拟建设智能采血管理及终端设备，提升采血窗口效率。未发布正式招标文件。",
    },
    evidence_source_urls: [
      "https://demo.medicalchannel.ai/sources/tj/intent/2026-03-15-phlebotomy",
    ],
    customer_context: {
      hospital_relationship:
        "与护理部关系稳定，可约到现场看采血窗口实际流程。",
      related_department: "护理部",
      internal_owner: "王护士长（客户确认）",
      product_capability:
        "暂无自有智能采血产品，需要寻找厂家或渠道合作后才能参与。",
      brand: null,
      can_find_manufacturer: true,
      can_channel_cooperate: true,
      relationship_strength: "strong",
      has_direct_product: false,
      notes: "王护士长反馈窗口排队和标本贴签是当前痛点，但未确认预算是否含软件。",
    },
    priority: { score: 71, label: "持续观察" },
    match_status: "STRONG_RELATION_NEED_MANUFACTURER",
    recommendation_mode: "OBSERVE",
    model_decision_status: "AWAITING_MODEL",
    model_block_reason: null,
    decision: null,
  },
  {
    rank: 4,
    opportunity_id: "tj-2026-004",
    facts: {
      hospital_name: "天津某区人民医院",
      purchaser: "天津某区人民医院",
      project_name: "全自动生化免疫流水线升级改造项目",
      project_stage: "公开招标（参数公示）",
      budget: null,
      deadline: "2026-05-06",
      expected_purchase_time: null,
      products: ["生化分析仪", "免疫分析仪", "轨道流水线"],
      public_contact: null,
      public_contact_phone: null,
      announcement_date: "2026-03-10",
      region: "天津",
      notice_summary:
        "参数公示提到生化免疫流水线升级，但未披露预算金额、联系人及完整技术参数附件。",
    },
    evidence_source_urls: [
      "https://demo.medicalchannel.ai/sources/tj/params/2026-03-10-lab-line",
    ],
    customer_context: {
      hospital_relationship: null,
      related_department: null,
      internal_owner: null,
      product_capability:
        "有生化/免疫产品线，可参与流水线中的分析仪部分；轨道系统可评估是否外协。",
      brand: "自有品牌（分析仪）",
      can_find_manufacturer: true,
      can_channel_cooperate: true,
      relationship_strength: "none",
      has_direct_product: true,
      notes: "该院此前无拜访记录，内部决策链未知。",
    },
    priority: { score: 68, label: "持续观察" },
    match_status: "NO_RELATION_DIRECT_PRODUCT",
    recommendation_mode: "OBSERVE",
    model_decision_status: "BLOCKED_GROUNDING",
    model_block_reason:
      "公开预算、联系人及关键技术参数缺失，无法完成依据核验，系统已阻断AI行动建议。",
    decision: null,
  },
  {
    rank: 5,
    opportunity_id: "tj-2026-005",
    facts: {
      hospital_name: "天津某妇幼保健院",
      purchaser: "天津某妇幼保健院",
      project_name: "全院医疗设备维保服务外包采购",
      project_stage: "竞争性磋商",
      budget: "人民币 240 万元/年",
      deadline: "2026-04-02",
      expected_purchase_time: "2026年二季度起服务",
      products: ["影像设备维保", "检验设备维保", "监护设备维保"],
      public_contact: "总务科（公告列部门）",
      public_contact_phone: null,
      announcement_date: "2026-03-06",
      region: "天津",
      notice_summary:
        "拟对全院部分影像、检验、监护设备进行维保服务外包。公告要求具备相应维修能力及响应时限，未列出设备清单明细。",
    },
    evidence_source_urls: [
      "https://demo.medicalchannel.ai/sources/tj/notice/2026-03-06-maintenance",
    ],
    customer_context: {
      hospital_relationship: "仅认识总务科一位同事，往来停留在打招呼层面。",
      related_department: "总务科",
      internal_owner: null,
      product_capability:
        "无自有维保团队，如需参与必须寻找厂家授权或本地服务渠道合作。",
      brand: null,
      can_find_manufacturer: true,
      can_channel_cooperate: true,
      relationship_strength: "weak",
      has_direct_product: false,
      notes: "客户确认自己不具备独立维保交付能力。",
    },
    priority: { score: 61, label: "持续观察" },
    match_status: "WEAK_RELATION_NEED_MANUFACTURER",
    recommendation_mode: "OBSERVE",
    model_decision_status: "MODEL_OUTPUT_REJECTED",
    model_block_reason:
      "模型输出包含未在公开信息中出现的推断内容，已拒绝展示，避免把猜测当成事实。",
    decision: null,
  },
];
