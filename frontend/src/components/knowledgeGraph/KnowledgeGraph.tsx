import { useCallback, useState } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { GraphNode } from "./GraphNode";
import { NodeDetailPanel } from "./NodeDetailPanel";
import { graphEdges, graphNodes, getNodeDetail } from "@/mock/knowledgeGraph";
import type { NodeDetail } from "@/types/knowledgeGraph";

const nodeTypes = { custom: GraphNode };

export function KnowledgeGraph() {
  const [detail, setDetail] = useState<NodeDetail | null>(null);

  const onNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
    const d = getNodeDetail(node.id);
    setDetail(d);
  }, []);

  const onPaneClick = useCallback(() => {
    setDetail(null);
  }, []);

  const onCloseDetail = useCallback(() => {
    setDetail(null);
  }, []);

  return (
    <div className="flex h-full">
      {/* Graph area */}
      <div className="flex-1">
        <ReactFlow
          nodes={graphNodes}
          edges={graphEdges}
          nodeTypes={nodeTypes}
          onNodeClick={onNodeClick}
          onPaneClick={onPaneClick}
          fitView
          fitViewOptions={{ padding: 0.3 }}
          attributionPosition="bottom-left"
        >
          <Background color="#e2e8f0" gap={24} />
          <Controls
            className="!rounded-lg !border !border-slate-200 !bg-white !shadow-sm"
            position="bottom-right"
          />
          <MiniMap
            nodeColor={(n) => {
              const colors: Record<string, string> = {
                enterprise: "#3b82f6",
                "legal-person": "#6366f1",
                supplier: "#059669",
                customer: "#0d9488",
                bank: "#f59e0b",
                tax: "#8b5cf6",
                policy: "#0ea5e9",
                knowledge: "#ec4899",
              };
              return colors[(n as any).data?.nodeType] ?? "#94a3b8";
            }}
            maskColor="rgb(15 23 42 / 0.08)"
            className="!rounded-lg !border !border-slate-200 !shadow-sm"
            position="bottom-left"
          />
        </ReactFlow>
      </div>

      {/* Detail panel — slides in from right */}
      <div
        className="transition-all duration-300 ease-in-out"
        style={{ width: detail ? 320 : 0, overflow: "hidden" }}
      >
        <NodeDetailPanel detail={detail} onClose={onCloseDetail} />
      </div>
    </div>
  );
}
