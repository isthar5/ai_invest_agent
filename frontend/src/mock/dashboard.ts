import type { DashboardMockData } from "@/types/dashboard";
import { workflowMock } from "./workflow";

export const dashboardMock: DashboardMockData = {
  enterprise: {
    companyName: "Northstar Robotics Co., Ltd.",
    industry: "Advanced Manufacturing / Industrial AI",
    creditRating: "AA-",
    healthScore: 86,
    funding: "$128.4M Series C",
    taxRating: "A",
    employeeCount: "1,240",
    tags: ["Strategic Supplier", "Export Eligible", "High R&D", "ISO 27001"],
    risk: {
      level: "medium",
      label: "Moderate Risk",
      summary: "Healthy fundamentals with increased exposure to overseas receivables.",
    },
    metrics: [
      { label: "Credit Rating", value: "AA-", tone: "blue" },
      { label: "Health Score", value: "86/100", tone: "emerald" },
      { label: "Funding", value: "$128.4M", tone: "slate" },
      { label: "Tax Rating", value: "A", tone: "amber" },
      { label: "Employees", value: "1,240", tone: "slate" },
    ],
  },
  suggestedQuestions: [
    {
      id: "cashflow-risk",
      title: "分析企业现金流压力",
      description: "评估流动性、应收账款账龄及短期债务集中度。",
    },
    {
      id: "industry-position",
      title: "行业竞争力分析",
      description: "对比增长、利润率及融资节奏与同业制造商的差异。",
    },
    {
      id: "credit-narrative",
      title: "生成授信分析报告",
      description: "汇总风险点、缓释措施及建议监控信号。",
    },
    {
      id: "sql-investigation",
      title: "识别企业风险信号",
      description: "识别内部数据中的异常税务、招聘和发票模式。",
    },
  ],
  workflow: workflowMock,
};
