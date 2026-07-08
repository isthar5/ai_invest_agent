import type { QuestionItem } from "@/types/chat";
import { cn } from "@/lib/utils";

interface QuestionButtonProps {
  question: QuestionItem;
  onClick: (question: QuestionItem) => void;
}

export function QuestionButton({ question, onClick }: QuestionButtonProps) {
  return (
    <button
      type="button"
      onClick={() => onClick(question)}
      className={cn(
        "w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-left text-sm text-slate-700",
        "transition-all duration-200 ease-out",
        "hover:border-primary/30 hover:bg-primary-light/60 hover:text-slate-900 hover:shadow-sm",
        "active:scale-[0.985]",
        "cursor-pointer",
      )}
    >
      {question.label}
    </button>
  );
}
