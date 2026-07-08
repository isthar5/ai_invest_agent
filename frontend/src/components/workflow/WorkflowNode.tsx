import { Clock3 } from "lucide-react";
import type { WorkflowNode as WorkflowNodeType } from "@/types/dashboard";
import { StatusBadge } from "./StatusBadge";

interface WorkflowNodeProps {
  node: WorkflowNodeType;
}

export function WorkflowNode({ node }: WorkflowNodeProps) {
  const hasTiming = node.startTime !== "--";

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm transition-all duration-200 hover:shadow-card-hover">
      {/* Header row: name + status */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold text-slate-950">{node.name}</h3>
          <p className="mt-1 text-sm leading-5 text-slate-500">{node.description}</p>
        </div>
        <StatusBadge status={node.status} />
      </div>

      {/* Timing row */}
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-slate-100 pt-3 text-xs text-slate-500">
        <span className="inline-flex items-center gap-1.5">
          <Clock3 className="h-3.5 w-3.5 text-slate-400" aria-hidden="true" />
          <span className="font-mono font-medium text-slate-700">{node.duration}</span>
        </span>

        {hasTiming && (
          <>
            <span>
              <span className="text-slate-400">Start </span>
              <span className="font-mono text-slate-700">{node.startTime}</span>
            </span>
            {node.endTime && (
              <span>
                <span className="text-slate-400">End </span>
                <span className="font-mono text-slate-700">{node.endTime}</span>
              </span>
            )}
          </>
        )}
      </div>
    </div>
  );
}
