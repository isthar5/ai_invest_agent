import { BarChart3, BookOpen, Database } from "lucide-react";
import type { AgentType, QuestionCategory, QuestionItem } from "@/types/chat";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { QuestionButton } from "./QuestionButton";

interface QuestionCategoryCardProps {
  category: QuestionCategory;
  onQuestionClick: (question: QuestionItem) => void;
  active?: boolean;
}

const iconMap: Record<string, React.ComponentType<{ className?: string }>> = {
  BarChart3,
  Database,
  BookOpen,
};

const agentBadge: Record<AgentType, { label: string; className: string }> = {
  quant: { label: "Quant", className: "border-purple-200 bg-purple-50 text-purple-700" },
  text2sql: { label: "Text2SQL", className: "border-amber-200 bg-amber-50 text-amber-700" },
  rag: { label: "RAG", className: "border-emerald-200 bg-emerald-50 text-emerald-700" },
};

export function QuestionCategoryCard({ category, onQuestionClick, active = false }: QuestionCategoryCardProps) {
  const Icon = iconMap[category.icon] ?? null;
  const badge = agentBadge[category.agentType];

  return (
    <div
      className={cn(
        "rounded-xl border bg-white p-4 shadow-card transition-all duration-200",
        active ? "border-blue-300 ring-2 ring-blue-200/50 shadow-card-elevated" : "border-slate-200 hover:shadow-card-hover",
      )}
    >
      {/* Header: icon + title + description */}
      <div className="mb-3 flex items-start gap-2.5">
        {Icon && (
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-blue-100 bg-blue-50 text-blue-700">
            <Icon className="h-4 w-4" aria-hidden="true" />
          </div>
        )}
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-slate-950">{category.title}</h3>
          <p className="text-xs text-slate-500">{category.description}</p>
        </div>
      </div>

      {/* Questions */}
      <div className="flex flex-col gap-2">
        {category.questions.map((question) => (
          <QuestionButton
            key={question.id}
            question={question}
            onClick={onQuestionClick}
          />
        ))}
      </div>

      {/* Agent badge — bottom-right */}
      <div className="mt-3 flex justify-end">
        <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold tracking-wide", badge.className)}>
          Powered by {badge.label} Agent
        </span>
      </div>
    </div>
  );
}
