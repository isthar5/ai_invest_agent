import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { ProfileRiskItem, ProfileRiskTone } from "@/types/enterprise";

const riskToneClass: Record<ProfileRiskTone, string> = {
  emerald: "bg-emerald-500",
  amber: "bg-amber-500",
  rose: "bg-rose-500",
  blue: "bg-blue-500",
  slate: "bg-slate-500",
};

const riskBadgeVariant: Record<ProfileRiskTone, "slate" | "blue" | "emerald" | "amber" | "rose"> = {
  emerald: "emerald",
  amber: "amber",
  rose: "rose",
  blue: "blue",
  slate: "slate",
};

interface RiskRowProps {
  risk: ProfileRiskItem;
}

export function RiskRow({ risk }: RiskRowProps) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger className="w-full">
          <div className="rounded-xl border border-slate-200 bg-white p-3 transition hover:border-blue-200 hover:shadow-sm">
            <div className="flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-medium text-slate-800">{risk.label}</p>
                <p className="mt-1 text-xs text-slate-500">评分 {risk.score}/100</p>
              </div>
              <Badge variant={riskBadgeVariant[risk.tone]}>{risk.status}</Badge>
            </div>
            <div className="mt-3 flex items-center gap-3">
              <Progress value={risk.score} className="h-1.5" />
              <span className={cn("h-2 w-2 shrink-0 rounded-full", riskToneClass[risk.tone])} />
            </div>
          </div>
        </TooltipTrigger>
        <TooltipContent>{risk.helper}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
