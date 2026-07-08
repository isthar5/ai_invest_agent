import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import {
  Banknote,
  BookOpen,
  Building2,
  FileText,
  Landmark,
  ReceiptText,
  User,
  Users,
} from "lucide-react";
import type { GraphNodeData, GraphNodeType } from "@/types/knowledgeGraph";
import { cn } from "@/lib/utils";

const nodeTypeConfig: Record<GraphNodeType, { icon: React.ComponentType<{ className?: string }>; borderColor: string; bgColor: string }> = {
  enterprise: { icon: Building2, borderColor: "border-blue-400", bgColor: "bg-blue-50" },
  "legal-person": { icon: User, borderColor: "border-indigo-400", bgColor: "bg-indigo-50" },
  supplier: { icon: Users, borderColor: "border-emerald-400", bgColor: "bg-emerald-50" },
  customer: { icon: Users, borderColor: "border-teal-400", bgColor: "bg-teal-50" },
  bank: { icon: Landmark, borderColor: "border-amber-400", bgColor: "bg-amber-50" },
  tax: { icon: ReceiptText, borderColor: "border-violet-400", bgColor: "bg-violet-50" },
  policy: { icon: FileText, borderColor: "border-sky-400", bgColor: "bg-sky-50" },
  knowledge: { icon: BookOpen, borderColor: "border-pink-400", bgColor: "bg-pink-50" },
};

function GraphNodeComponent({ data, selected }: NodeProps) {
  const nodeData = data as unknown as GraphNodeData;
  const config = nodeTypeConfig[nodeData.nodeType] ?? nodeTypeConfig.enterprise;
  const Icon = config.icon;

  return (
    <div
      className={cn(
        "relative min-w-[160px] rounded-xl border-2 bg-white px-4 py-3 shadow-card transition-all duration-200",
        config.borderColor,
        selected && "shadow-card-elevated ring-2 ring-blue-300 ring-offset-2",
        !selected && "hover:shadow-card-hover hover:scale-[1.03]",
      )}
    >
      <Handle type="target" position={Position.Top} className="!bg-slate-300" />
      <Handle type="source" position={Position.Bottom} className="!bg-slate-300" />

      {/* Icon + Label */}
      <div className="flex items-center gap-2.5">
        <div className={cn("flex h-8 w-8 items-center justify-center rounded-lg border", config.borderColor, config.bgColor)}>
          <Icon className="h-4 w-4" aria-hidden="true" />
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-slate-950">{nodeData.label}</p>
          <p className="text-xs text-slate-500">{nodeData.category}</p>
        </div>
      </div>
    </div>
  );
}

export const GraphNode = memo(GraphNodeComponent);
