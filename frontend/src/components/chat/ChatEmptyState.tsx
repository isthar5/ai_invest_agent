import { Loader2, Sparkles } from "lucide-react";
import type { AgentType, QuestionCategory, QuestionItem } from "@/types/chat";
import { ChatInput } from "./ChatInput";
import { QuestionCategoryCard } from "./QuestionCategoryCard";

interface ChatEmptyStateProps {
  categories: QuestionCategory[];
  activeAgentType: AgentType | null;
  inputValue: string;
  onQuestionClick: (question: QuestionItem, agentType: AgentType) => void;
  onSend: (text: string) => void;
  /** Workflow execution result — shown when available */
  answer: string | null;
  /** Whether a workflow is currently executing */
  isRunning: boolean;
}

export function ChatEmptyState({
  categories, activeAgentType, inputValue,
  onQuestionClick, onSend, answer, isRunning,
}: ChatEmptyStateProps) {
  return (
    <div className="flex h-full flex-col">
      {/* Scrollable content area */}
      <div className="flex flex-1 items-center justify-center overflow-y-auto px-8 py-8">
        <div className="w-full max-w-[800px] space-y-6">

          {/* ── Result view (when answer is available) ── */}
          {answer ? (
            <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-card">
              <div className="mb-4 flex items-center gap-2">
                <Sparkles className="h-5 w-5 text-blue-600" />
                <h2 className="text-lg font-semibold text-slate-950">分析结果</h2>
              </div>
              <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-slate-700">
                {answer}
              </pre>
            </div>
          ) : isRunning ? (
            /* ── Running view ── */
            <div className="text-center">
              <Loader2 className="mx-auto h-8 w-8 animate-spin text-blue-500" />
              <p className="mt-4 text-sm text-slate-500">
                正在执行 {activeAgentType === "quant" ? "Quant" : activeAgentType === "text2sql" ? "Text2SQL" : "RAG"} 分析流程...
              </p>
              <p className="mt-1 text-xs text-slate-400">请观察右侧 Workflow Trace 面板</p>
            </div>
          ) : (
            /* ── Idle view: title + cards ── */
            <>
              <div className="text-center">
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl border border-blue-100 bg-blue-50 text-blue-700 shadow-sm">
                  <Sparkles className="h-5 w-5" aria-hidden="true" />
                </div>
                <h1 className="mt-5 text-2xl font-semibold tracking-normal text-slate-950">
                  企业 AI 分析助手
                </h1>
                <p className="mx-auto mt-3 max-w-lg text-sm leading-6 text-slate-500">
                  不同类型的问题将自动路由到对应的智能分析能力，选择下方推荐问题开始体验。
                </p>
              </div>

              <div className="grid gap-4 md:grid-cols-3">
                {categories.map((category) => (
                  <QuestionCategoryCard
                    key={category.id}
                    category={category}
                    onQuestionClick={(q) => onQuestionClick(q, category.agentType)}
                    active={activeAgentType === category.agentType}
                  />
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Fixed input bar at bottom */}
      <div className="shrink-0 border-t border-slate-200 bg-white px-8 py-4">
        <div className="mx-auto max-w-[800px]">
          <ChatInput onSend={onSend} value={inputValue} />
        </div>
      </div>
    </div>
  );
}
