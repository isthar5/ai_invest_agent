import type { QuestionCategory } from "@/types/chat";

export const chatMock: QuestionCategory[] = [
  {
    id: "quant",
    title: "财务分析",
    description: "盈利能力、现金流、估值分析",
    icon: "BarChart3",
    agentType: "quant",
    questions: [
      { id: "q-1", label: "盈利能力分析", text: "分析万华化学近三年盈利能力变化趋势" },
      { id: "q-2", label: "现金流分析", text: "评估万华化学现金流压力与短期偿债能力" },
      { id: "q-3", label: "企业估值", text: "对万华化学进行同业估值对比分析" },
    ],
  },
  {
    id: "text2sql",
    title: "数据查询",
    description: "结构化数据精准查询与排名",
    icon: "Database",
    agentType: "text2sql",
    questions: [
      { id: "t-1", label: "营业收入查询", text: "查询万华化学近五年各季度营业收入" },
      { id: "t-2", label: "利润排名", text: "对比化工行业头部企业净利润排名" },
      { id: "t-3", label: "资产负债率", text: "查询万华化学最新资产负债率及行业分位数" },
    ],
  },
  {
    id: "rag",
    title: "企业知识",
    description: "公司概况、行业背景、政策解读",
    icon: "BookOpen",
    agentType: "rag",
    questions: [
      { id: "r-1", label: "公司介绍", text: "介绍万华化学主营业务与核心竞争优势" },
      { id: "r-2", label: "行业分析", text: "分析聚氨酯行业竞争格局与发展趋势" },
      { id: "r-3", label: "政策解读", text: "解读最新化工行业环保政策对企业的影响" },
    ],
  },
];
