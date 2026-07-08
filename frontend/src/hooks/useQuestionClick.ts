import { useCallback, useMemo, useState } from "react";
import type { AgentType, QuestionItem } from "@/types/chat";
import type { WorkflowNode } from "@/types/dashboard";
import { agentWorkflows, defaultWorkflow } from "@/mock/workflow";
import { classifyIntent } from "@/api/router";

export function useQuestionClick() {
  const [selectedQuestion, setSelectedQuestion] = useState<QuestionItem | null>(null);
  const [activeAgentType, setActiveAgentType] = useState<AgentType | null>(null);
  const [inputValue, setInputValue] = useState("");
  const [routerLoading, setRouterLoading] = useState(false);

  const activeWorkflow: WorkflowNode[] = useMemo(() => {
    if (!activeAgentType) return defaultWorkflow;
    return agentWorkflows[activeAgentType] ?? defaultWorkflow;
  }, [activeAgentType]);

  const handleQuestionClick = useCallback(async (question: QuestionItem, agentType: AgentType) => {
    // 1. Optimistic UI: fill input + switch workflow immediately
    setSelectedQuestion(question);
    setActiveAgentType(agentType);
    setInputValue(question.text);

    // 2. Call real Router API
    setRouterLoading(true);
    const backendWorkflow = await classifyIntent(question.text, agentType);
    setRouterLoading(false);

    // 3. If backend disagrees with optimistic guess, update
    if (backendWorkflow !== agentType) {
      console.log("[Router] backend override:", agentType, "→", backendWorkflow);
      setActiveAgentType(backendWorkflow);
    }
  }, []);

  const handleSend = useCallback(async (text: string) => {
    console.log("[Chat] Send:", text);
    setInputValue("");
    setSelectedQuestion(null);
    // 默认走 RAG 流程，然后等 Router API 返回后切换
    setActiveAgentType("rag");
    setRouterLoading(true);
    const backendWorkflow = await classifyIntent(text, "rag");
    setRouterLoading(false);
    setActiveAgentType(backendWorkflow);
    return backendWorkflow;
  }, []);

  return {
    selectedQuestion,
    activeAgentType,
    activeWorkflow,
    inputValue,
    routerLoading,
    handleQuestionClick,
    handleSend,
  };
}
