import { useState } from "react";
import { ChatEmptyState } from "@/components/chat/ChatEmptyState";
import { KnowledgeGraph } from "@/components/knowledgeGraph/KnowledgeGraph";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { useQuestionClick } from "@/hooks/useQuestionClick";
import { useWorkflowStream } from "@/hooks/useWorkflowStream";
import { chatMock } from "@/mock/chat";
import { dashboardMock } from "@/mock/dashboard";
import { cn } from "@/lib/utils";

type ViewMode = "chat" | "graph";

export default function Dashboard() {
  const {
    activeAgentType,
    inputValue,
    handleQuestionClick,
    handleSend,
  } = useQuestionClick();

  const { nodes: liveNodes, isRunning, answer, startWorkflow } = useWorkflowStream();

  const [view, setView] = useState<ViewMode>("chat");

  // When question is clicked → start real workflow
  const onQuestionClick = async (question: any, agentType: any) => {
    await handleQuestionClick(question, agentType);
    startWorkflow(question.text, agentType);
  };

  // 用户手动输入 → 路由分类 → 启动 workflow
  const onSendWithWorkflow = async (text: string) => {
    const agentType = await handleSend(text);
    startWorkflow(text, agentType);
  };

  // Use live nodes if running or answer available, otherwise default
  const displayWorkflow = (isRunning || answer) ? liveNodes : undefined;

  return (
    <DashboardLayout
      enterprise={dashboardMock.enterprise}
      workflow={displayWorkflow ?? dashboardMock.workflow}
    >
      <div className="flex h-full flex-col">
        {/* View toggle */}
        <div className="shrink-0 border-b border-slate-200 bg-white px-8 py-2">
          <div className="flex gap-1">
            <button
              type="button"
              onClick={() => setView("chat")}
              className={cn(
                "rounded-lg px-4 py-1.5 text-sm font-medium transition-colors",
                view === "chat"
                  ? "bg-blue-50 text-blue-700"
                  : "text-slate-500 hover:text-slate-700 hover:bg-slate-50",
              )}
            >
              分析助手
            </button>
            <button
              type="button"
              onClick={() => setView("graph")}
              className={cn(
                "rounded-lg px-4 py-1.5 text-sm font-medium transition-colors",
                view === "graph"
                  ? "bg-blue-50 text-blue-700"
                  : "text-slate-500 hover:text-slate-700 hover:bg-slate-50",
              )}
            >
              知识图谱
            </button>
          </div>
        </div>

        {/* View content */}
        <div className="flex-1 overflow-hidden">
          {view === "chat" ? (
            <ChatEmptyState
              categories={chatMock}
              activeAgentType={activeAgentType}
              inputValue={inputValue}
              onQuestionClick={onQuestionClick}
              onSend={onSendWithWorkflow}
              answer={answer}
              isRunning={isRunning}
            />
          ) : (
            <KnowledgeGraph />
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
