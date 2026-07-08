export type RiskLevel = "low" | "medium" | "high";
export type WorkflowStatus = "pending" | "running" | "success" | "failed";
export type Tone = "slate" | "blue" | "emerald" | "amber" | "rose";

export interface EnterpriseMetric {
  label: string;
  value: string;
  tone: Tone;
}

export interface EnterpriseProfile {
  companyName: string;
  industry: string;
  creditRating: string;
  healthScore: number;
  funding: string;
  taxRating: string;
  employeeCount: string;
  tags: string[];
  risk: {
    level: RiskLevel;
    label: string;
    summary: string;
  };
  metrics: EnterpriseMetric[];
}

export interface SuggestedQuestion {
  id: string;
  title: string;
  description: string;
}

export interface WorkflowNode {
  id: string;
  name: string;
  status: WorkflowStatus;
  startTime: string;
  endTime?: string;
  duration: string;
  description: string;
}

export interface DashboardMockData {
  enterprise: EnterpriseProfile;
  suggestedQuestions: SuggestedQuestion[];
  workflow: WorkflowNode[];
}
