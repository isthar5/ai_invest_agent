import { X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import type { NodeDetail } from "@/types/knowledgeGraph";

interface NodeDetailPanelProps {
  detail: NodeDetail | null;
  onClose: () => void;
}

const nodeTypeLabel: Record<string, string> = {
  enterprise: "核心企业",
  "legal-person": "法人",
  supplier: "供应商",
  customer: "客户",
  bank: "银行",
  tax: "税务",
  policy: "政府政策",
  knowledge: "知识库",
};

export function NodeDetailPanel({ detail, onClose }: NodeDetailPanelProps) {
  if (!detail) return null;

  return (
    <aside className={cn("flex h-full flex-col overflow-hidden border-l border-slate-200 bg-white shadow-lg")}>
      {/* Header */}
      <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
        <div className="min-w-0">
          <h2 className="truncate text-base font-semibold text-slate-950">{detail.label}</h2>
          <p className="text-xs text-slate-500">{nodeTypeLabel[detail.nodeType] ?? detail.nodeType}</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 space-y-5 overflow-y-auto p-5">
        {/* Properties */}
        <section>
          <h3 className="mb-3 text-sm font-semibold text-slate-950">属性</h3>
          <div className="divide-y divide-slate-100 rounded-lg border border-slate-200">
            {detail.properties.map((prop) => (
              <div key={prop.key} className="flex items-center justify-between gap-3 px-3 py-2.5 text-sm">
                <span className="text-slate-500">{prop.key}</span>
                <span className="font-medium text-slate-900">{prop.value}</span>
              </div>
            ))}
          </div>
        </section>

        <Separator />

        {/* Tags */}
        <section>
          <h3 className="mb-3 text-sm font-semibold text-slate-950">标签</h3>
          <div className="flex flex-wrap gap-2">
            {detail.tags.map((tag) => (
              <Badge key={tag} variant="blue">
                {tag}
              </Badge>
            ))}
          </div>
        </section>

        <Separator />

        {/* Relationships */}
        <section>
          <h3 className="mb-3 text-sm font-semibold text-slate-950">关联关系</h3>
          <div className="space-y-2">
            {detail.relationships.length === 0 && (
              <p className="text-sm text-slate-400">暂无关联关系</p>
            )}
            {detail.relationships.map((rel, i) => {
              const targetNode = rel.target;
              return (
                <div key={`${rel.target}-${i}`} className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm">
                  <span className={cn(
                    "inline-flex h-1.5 w-1.5 shrink-0 rounded-full",
                    rel.direction === "out" ? "bg-blue-500" : "bg-emerald-500",
                  )} />
                  <span className="text-slate-700">
                    {rel.direction === "out" ? "→" : "←"} {rel.label}
                  </span>
                  <span className="ml-auto text-xs text-slate-400">{targetNode}</span>
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </aside>
  );
}
