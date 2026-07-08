import type { WorkflowNode as WorkflowNodeType } from "@/types/dashboard";
import { WorkflowEdge } from "./WorkflowEdge";
import { WorkflowNode } from "./WorkflowNode";

interface WorkflowTimelineProps {
  nodes: WorkflowNodeType[];
}

export function WorkflowTimeline({ nodes }: WorkflowTimelineProps) {
  if (!nodes.length) return null;

  return (
    <div className="space-y-1">
      {nodes.map((node, index) => {
        const isLast = index === nodes.length - 1;

        return (
          <div key={node.id}>
            <WorkflowNode node={node} />
            {!isLast && (
              <WorkflowEdge
                fromStatus={node.status}
                toStatus={nodes[index + 1].status}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
