import { CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";
import type { WorkflowStatus } from "@/types/dashboard";
import { cn } from "@/lib/utils";

interface StatusBadgeProps {
  status: WorkflowStatus;
}

const statusConfig: Record<WorkflowStatus, { label: string; icon: React.ComponentType<{ className?: string }>; className: string }> = {
  success: {
    label: "Success",
    icon: CheckCircle2,
    className: "border-emerald-200 bg-emerald-50 text-emerald-700",
  },
  running: {
    label: "Running",
    icon: Loader2,
    className: "border-blue-200 bg-blue-50 text-blue-700",
  },
  pending: {
    label: "Pending",
    icon: Circle,
    className: "border-slate-200 bg-slate-50 text-slate-500",
  },
  failed: {
    label: "Failed",
    icon: XCircle,
    className: "border-rose-200 bg-rose-50 text-rose-700",
  },
};

export function StatusBadge({ status }: StatusBadgeProps) {
  const config = statusConfig[status];
  const Icon = config.icon;

  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium", config.className)}>
      <Icon className={cn("h-3.5 w-3.5", status === "running" && "animate-spin")} aria-hidden="true" />
      {config.label}
    </span>
  );
}
