import { WorkflowTrace } from "@/components/workflow/WorkflowTrace";
import type { WorkflowNode } from "@/types/dashboard";

interface RightPanelProps {
  workflow: WorkflowNode[];
}

export function RightPanel({ workflow }: RightPanelProps) {
  return (
    <aside className="flex h-full flex-col overflow-hidden border-l border-slate-200 bg-slate-50 p-5">
      <WorkflowTrace workflow={workflow} />
    </aside>
  );
}
