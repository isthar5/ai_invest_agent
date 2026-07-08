import { SectionCard } from "@/components/ui/SectionCard";
import { SectionTitle } from "@/components/ui/SectionTitle";
import { Separator } from "@/components/ui/separator";
import type { WorkflowNode as WorkflowNodeType } from "@/types/dashboard";
import { WorkflowTimeline } from "./WorkflowTimeline";

interface WorkflowTraceProps {
  workflow: WorkflowNodeType[];
}

export function WorkflowTrace({ workflow }: WorkflowTraceProps) {
  return (
    <SectionCard className="flex h-full flex-col p-0">
      {/* Fixed header */}
      <div className="shrink-0 p-5">
        <SectionTitle
          title="Workflow Trace"
          description="Mock orchestration path for this enterprise analysis."
        />
      </div>
      <Separator />

      {/* Scrollable timeline */}
      <div className="flex-1 overflow-y-auto p-5">
        <WorkflowTimeline nodes={workflow} />
      </div>
    </SectionCard>
  );
}
