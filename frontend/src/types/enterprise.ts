export type ProfileMetricTone = "blue" | "emerald" | "amber" | "slate" | "rose";
export type ProfileRiskTone = "emerald" | "amber" | "rose" | "blue" | "slate";
export type ProfileRiskKey = "cashFlow" | "tax" | "contract" | "policy";
export type ProfileMetricId =
  | "health-score"
  | "revenue"
  | "credit"
  | "tax"
  | "market-cap"
  | "profit-growth"
  | "esg"
  | "risk-level";

export interface ProfileMetric {
  id: ProfileMetricId;
  label: string;
  value: string;
  helper: string;
  tone: ProfileMetricTone;
}

export interface ProfileTag {
  id: string;
  label: string;
}

export interface ProfileRiskItem {
  id: ProfileRiskKey;
  label: string;
  status: string;
  score: number;
  helper: string;
  tone: ProfileRiskTone;
}

export interface EnterpriseProfileMock {
  stockCode: string;
  company: {
    name: string;
    industry: string;
    founded: string;
    employees: string;
    avatarLabel: string;
  };
  metrics: ProfileMetric[];
  tags: ProfileTag[];
  risks: ProfileRiskItem[];
}