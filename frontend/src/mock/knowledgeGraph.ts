import type { KnowledgeGraphNode, KnowledgeGraphEdge, NodeDetail } from "@/types/knowledgeGraph";

export const graphNodes: KnowledgeGraphNode[] = [
  {
    id: "enterprise",
    type: "custom",
    position: { x: 480, y: 280 },
    data: {
      label: "万华化学",
      nodeType: "enterprise",
      category: "核心企业",
      properties: [
        { key: "股票代码", value: "600309" },
        { key: "行业", value: "化学制品" },
        { key: "成立", value: "1998年" },
        { key: "员工", value: "约2.5万人" },
        { key: "营收", value: "2,032亿" },
      ],
      tags: ["聚氨酯龙头", "全球化运营", "MDI全球领先"],
    },
  },
  {
    id: "legal-person",
    type: "custom",
    position: { x: 200, y: 100 },
    data: {
      label: "法人代表",
      nodeType: "legal-person",
      category: "治理主体",
      properties: [
        { key: "姓名", value: "廖增太" },
        { key: "持股比例", value: "2.36%" },
        { key: "任期", value: "2016年至今" },
      ],
      tags: ["实际控制人", "董事长"],
    },
  },
  {
    id: "supplier",
    type: "custom",
    position: { x: 100, y: 400 },
    data: {
      label: "原材料供应商",
      nodeType: "supplier",
      category: "供应链",
      properties: [
        { key: "供应商数量", value: "23家核心" },
        { key: "集中度", value: "中等" },
        { key: "主要原料", value: "纯苯、煤炭" },
      ],
      tags: ["化工原料", "长期合作", "Tier 1"],
    },
  },
  {
    id: "customer",
    type: "custom",
    position: { x: 860, y: 400 },
    data: {
      label: "下游客户",
      nodeType: "customer",
      category: "销售网络",
      properties: [
        { key: "客户数量", value: "300+" },
        { key: "覆盖区域", value: "全球50+国家" },
        { key: "主要行业", value: "汽车、建筑、家电" },
      ],
      tags: ["全球化", "B2B", "长期合约"],
    },
  },
  {
    id: "bank",
    type: "custom",
    position: { x: 100, y: 600 },
    data: {
      label: "合作银行",
      nodeType: "bank",
      category: "金融服务",
      properties: [
        { key: "授信总额", value: "500亿" },
        { key: "主要银行", value: "工商银行、建设银行" },
        { key: "贷款利率", value: "LPR-20bp" },
      ],
      tags: ["信用良好", "战略合作"],
    },
  },
  {
    id: "tax",
    type: "custom",
    position: { x: 500, y: 600 },
    data: {
      label: "税务机构",
      nodeType: "tax",
      category: "监管合规",
      properties: [
        { key: "纳税评级", value: "A级" },
        { key: "年纳税额", value: "约45亿" },
        { key: "税务优惠", value: "高新技术企业" },
      ],
      tags: ["合规", "A级纳税人"],
    },
  },
  {
    id: "policy",
    type: "custom",
    position: { x: 860, y: 100 },
    data: {
      label: "政府政策",
      nodeType: "policy",
      category: "政策环境",
      properties: [
        { key: "产业政策", value: "新材料支持" },
        { key: "补贴类型", value: "研发补贴" },
        { key: "政策周期", value: "2024-2027" },
      ],
      tags: ["政策利好", "战略新兴"],
    },
  },
  {
    id: "knowledge",
    type: "custom",
    position: { x: 860, y: 600 },
    data: {
      label: "知识库",
      nodeType: "knowledge",
      category: "数据资产",
      properties: [
        { key: "文档数量", value: "1,250份" },
        { key: "年报", value: "2022-2025" },
        { key: "行业报告", value: "45份" },
      ],
      tags: ["RAG", "向量检索"],
    },
  },
];

export const graphEdges: KnowledgeGraphEdge[] = [
  {
    id: "e-legal-enterprise",
    source: "legal-person",
    target: "enterprise",
    data: { label: "投资", edgeType: "invest" },
    label: "投资",
    animated: true,
    style: { stroke: "#3b82f6" },
  },
  {
    id: "e-supplier-enterprise",
    source: "supplier",
    target: "enterprise",
    data: { label: "供应", edgeType: "supply" },
    label: "供应",
    animated: true,
    style: { stroke: "#059669" },
  },
  {
    id: "e-enterprise-customer",
    source: "enterprise",
    target: "customer",
    data: { label: "供应", edgeType: "supply" },
    label: "供应",
    animated: true,
    style: { stroke: "#059669" },
  },
  {
    id: "e-bank-enterprise",
    source: "bank",
    target: "enterprise",
    data: { label: "贷款", edgeType: "loan" },
    label: "贷款",
    animated: true,
    style: { stroke: "#f59e0b" },
  },
  {
    id: "e-enterprise-tax",
    source: "enterprise",
    target: "tax",
    data: { label: "纳税", edgeType: "tax" },
    label: "纳税",
    animated: true,
    style: { stroke: "#8b5cf6" },
  },
  {
    id: "e-policy-enterprise",
    source: "policy",
    target: "enterprise",
    data: { label: "补贴", edgeType: "subsidy" },
    label: "补贴",
    animated: true,
    style: { stroke: "#0ea5e9" },
  },
  {
    id: "e-knowledge-enterprise",
    source: "knowledge",
    target: "enterprise",
    data: { label: "知识检索", edgeType: "reference" },
    label: "知识检索",
    animated: true,
    style: { stroke: "#ec4899" },
  },
];

export function getNodeDetail(nodeId: string): NodeDetail | null {
  const node = graphNodes.find((n) => n.id === nodeId);
  if (!node) return null;

  const relationships = graphEdges
    .filter((e) => e.source === nodeId || e.target === nodeId)
    .map((e) => ({
      target: e.source === nodeId ? e.target : e.source,
      label: e.data?.label ?? "",
      direction: e.source === nodeId ? ("out" as const) : ("in" as const),
    }));

  return {
    nodeId: node.id,
    label: node.data.label,
    nodeType: node.data.nodeType,
    category: node.data.category,
    properties: node.data.properties,
    tags: node.data.tags,
    relationships,
  };
}
