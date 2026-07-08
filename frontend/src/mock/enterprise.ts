import type { EnterpriseProfileMock } from "@/types/profile";

export const enterpriseProfiles: EnterpriseProfileMock[] = [
  {
    stockCode: "600309",
    company: {
      name: "万华化学",
      industry: "化学制品",
      founded: "1998年",
      employees: "约2.5万人",
      avatarLabel: "万华",
    },
    metrics: [
      {
        id: "health-score",
        label: "经营健康",
        value: "87",
        helper: "基于财务质量、盈利韧性、偿债压力与经营稳定性的综合评分。",
        tone: "emerald",
      },
      {
        id: "revenue",
        label: "营收规模",
        value: "2,032亿",
        helper: "2025年全年营业收入。",
        tone: "blue",
      },
      {
        id: "credit",
        label: "信用评级",
        value: "AA",
        helper: "结合企业规模、现金流、偿债能力与公开信用信息形成的前端展示评级。",
        tone: "amber",
      },
      {
        id: "tax",
        label: "税务评级",
        value: "A",
        helper: "税务合规与纳税信用等级。",
        tone: "slate",
      },
      {
        id: "market-cap",
        label: "总市值",
        value: "2,224亿",
        helper: "来自当前前端 Mock 行情数据。",
        tone: "blue",
      },
      {
        id: "profit-growth",
        label: "利润增长",
        value: "+20.62%",
        helper: "2026年一季度同比增长表现。",
        tone: "emerald",
      },
      {
        id: "esg",
        label: "ESG评级",
        value: "AAA",
        helper: "秩鼎评级口径。",
        tone: "emerald",
      },
      {
        id: "risk-level",
        label: "风险等级",
        value: "中",
        helper: "基于资产负债率、行业周期与经营波动的综合前端判断。",
        tone: "amber",
      },
    ],
    tags: [
      { id: "polyurethane-leader", label: "聚氨酯龙头" },
      { id: "global-operation", label: "全球化运营" },
      { id: "tech-innovation", label: "技术创新" },
      { id: "mdi-leader", label: "MDI全球领先" },
      { id: "srdi", label: "专精特新" },
    ],
    risks: [
      {
        id: "cashFlow",
        label: "现金流",
        status: "稳健",
        score: 86,
        helper: "大规模经营现金流具备韧性，但化工周期波动仍需持续跟踪。",
        tone: "emerald",
      },
      {
        id: "tax",
        label: "税务",
        status: "稳定",
        score: 90,
        helper: "税务评级为 A，合规表现稳定。",
        tone: "blue",
      },
      {
        id: "contract",
        label: "合同",
        status: "关注",
        score: 78,
        helper: "全球化运营下需关注长约价格、原材料传导与海外客户履约节奏。",
        tone: "amber",
      },
      {
        id: "policy",
        label: "政策",
        status: "中性",
        score: 72,
        helper: "化工制品受环保、安全生产与出口政策影响较高。",
        tone: "amber",
      },
    ],
  },
  {
    stockCode: "000001",
    company: {
      name: "平安银行",
      industry: "银行",
      founded: "1987年",
      employees: "约4.3万人",
      avatarLabel: "平安",
    },
    metrics: [
      { id: "health-score", label: "经营健康", value: "84", helper: "银行资产质量、资本充足率与盈利稳定性综合评分。", tone: "emerald" },
      { id: "revenue", label: "营收规模", value: "Mock", helper: "示例企业数据，待接入真实数据源。", tone: "slate" },
      { id: "credit", label: "信用评级", value: "AA", helper: "前端 Mock 信用评级。", tone: "blue" },
      { id: "tax", label: "税务评级", value: "A", helper: "前端 Mock 税务评级。", tone: "slate" },
    ],
    tags: [
      { id: "finance", label: "金融服务" },
      { id: "listed", label: "A股上市" },
      { id: "risk-control", label: "风控体系" },
    ],
    risks: [
      { id: "cashFlow", label: "现金流", status: "稳定", score: 82, helper: "示例风险数据。", tone: "blue" },
      { id: "tax", label: "税务", status: "稳定", score: 88, helper: "示例风险数据。", tone: "blue" },
      { id: "contract", label: "合同", status: "低", score: 80, helper: "示例风险数据。", tone: "emerald" },
      { id: "policy", label: "政策", status: "关注", score: 76, helper: "示例风险数据。", tone: "amber" },
    ],
  },
  {
    stockCode: "300750",
    company: {
      name: "宁德时代",
      industry: "电池",
      founded: "2011年",
      employees: "约11万人",
      avatarLabel: "宁德",
    },
    metrics: [
      { id: "health-score", label: "经营健康", value: "89", helper: "新能源制造企业综合经营评分。", tone: "emerald" },
      { id: "revenue", label: "营收规模", value: "Mock", helper: "示例企业数据，待接入真实数据源。", tone: "slate" },
      { id: "credit", label: "信用评级", value: "AA", helper: "前端 Mock 信用评级。", tone: "blue" },
      { id: "tax", label: "税务评级", value: "A", helper: "前端 Mock 税务评级。", tone: "slate" },
    ],
    tags: [
      { id: "battery", label: "动力电池" },
      { id: "global", label: "全球供应链" },
      { id: "innovation", label: "技术创新" },
    ],
    risks: [
      { id: "cashFlow", label: "现金流", status: "稳健", score: 86, helper: "示例风险数据。", tone: "emerald" },
      { id: "tax", label: "税务", status: "稳定", score: 89, helper: "示例风险数据。", tone: "blue" },
      { id: "contract", label: "合同", status: "关注", score: 77, helper: "示例风险数据。", tone: "amber" },
      { id: "policy", label: "政策", status: "利好", score: 84, helper: "示例风险数据。", tone: "emerald" },
    ],
  },
];

export const defaultEnterpriseStockCode = "600309";

export function getEnterpriseProfileByStockCode(stockCode: string): EnterpriseProfileMock | undefined {
  return enterpriseProfiles.find((profile) => profile.stockCode === stockCode.trim());
}