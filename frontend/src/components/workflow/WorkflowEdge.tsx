import type { WorkflowStatus } from "@/types/dashboard";
import { cn } from "@/lib/utils";

interface WorkflowEdgeProps {
  fromStatus: WorkflowStatus;
  toStatus: WorkflowStatus;
}

const edgeColor: Record<WorkflowStatus, string> = {
  success: "bg-emerald-300",
  running: "bg-blue-300",
  pending: "bg-slate-200",
  failed: "bg-rose-300",
};

export function WorkflowEdge({ fromStatus }: WorkflowEdgeProps) {
  const isActive = fromStatus === "running";

  return (
    <div className="flex justify-center py-1">
      <div className="relative h-8 w-px overflow-hidden bg-slate-200">
        <div
          className={cn(
            "absolute inset-x-0 top-0 w-px rounded-full",
            edgeColor[fromStatus],
            isActive && "animate-pulse",
          )}
          style={{ height: fromStatus === "pending" ? "0%" : "100%" }}
        />
        {isActive && (
          <div
            className="absolute inset-x-0 top-0 w-px animate-pulse rounded-full bg-blue-400"
            style={{ height: "60%" }}
          />
        )}
      </div>
    </div>
  );
}
