/** Chat workspace types */

export type AgentType = "quant" | "text2sql" | "rag";

export interface QuestionItem {
  id: string;
  label: string;
  /** Full question text that fills the input when clicked */
  text: string;
}

export interface QuestionCategory {
  id: string;
  title: string;
  description: string;
  icon: string;
  agentType: AgentType;
  questions: QuestionItem[];
}
