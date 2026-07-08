import type { ComponentType } from "react";
import {
  BadgePercent,
  Banknote,
  BarChart3,
  FileCheck2,
  Info,
  Leaf,
  ReceiptText,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { ProfileMetric, ProfileMetricId } from "@/types/enterprise";

const metricIcons: Record<ProfileMetricId, ComponentType<{ className?: string }>> = {
  "health-score": ShieldCheck,
  revenue: BarChart3,
  credit: FileCheck2,
  tax: ReceiptText,
  "market-cap": Banknote,
  "profit-growth": BadgePercent,
  esg: Leaf,
  "risk-level": ShieldAlert,
};

const metricToneClass: Record<ProfileMetric["tone"], string> = {
  blue: "border-blue-200 bg-blue-50 text-blue-700",
  emerald: "border-emerald-200 bg-emerald-50 text-emerald-700",
  amber: "border-amber-200 bg-amber-50 text-amber-700",
  slate: "border-slate-200 bg-slate-50 text-slate-700",
  rose: "border-rose-200 bg-rose-50 text-rose-700",
};

interface MetricCardProps {
  metric: ProfileMetric;
}

export function MetricCard({ metric }: MetricCardProps) {
  const Icon = metricIcons[metric.id];

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger className="w-full">
          <div className="w-full rounded-xl border border-slate-200 bg-slate-50 p-3 text-left transition hover:border-blue-200 hover:bg-white hover:shadow-sm">
            <div className="flex items-center justify-between gap-2">
              <div className={cn("flex h-8 w-8 items-center justify-center rounded-lg border", metricToneClass[metric.tone])}>
                <Icon className="h-4 w-4" aria-hidden="true" />
              </div>
              <Info className="h-3.5 w-3.5 text-slate-400" aria-hidden="true" />
            </div>
            <p className="mt-3 text-xs font-medium text-slate-500">{metric.label}</p>
            <p className="mt-1 text-lg font-semibold leading-6 text-slate-950">{metric.value}</p>
          </div>
        </TooltipTrigger>
        <TooltipContent>{metric.helper}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
