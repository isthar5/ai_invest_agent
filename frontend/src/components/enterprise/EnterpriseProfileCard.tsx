import { useMemo, useState, type ComponentType } from "react";
import {
  Building2,
  CalendarDays,
  Search,
  UsersRound,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { TooltipProvider } from "@/components/ui/tooltip";
import { defaultEnterpriseStockCode, getEnterpriseProfileByStockCode } from "@/mock/enterprise";
import type { EnterpriseProfile } from "@/types/dashboard";
import { MetricCard } from "./MetricCard";
import { RiskRow } from "./RiskRow";

interface EnterpriseProfileCardProps {
  enterprise?: EnterpriseProfile;
}

export function EnterpriseProfileCard(_: EnterpriseProfileCardProps) {
  const [inputCode, setInputCode] = useState(defaultEnterpriseStockCode);
  const [activeCode, setActiveCode] = useState(defaultEnterpriseStockCode);

  const profile = useMemo(() => getEnterpriseProfileByStockCode(activeCode), [activeCode]);
  const defaultProfile = useMemo(() => getEnterpriseProfileByStockCode(defaultEnterpriseStockCode), []);
  const displayProfile = profile ?? defaultProfile;

  const handleSwitchCompany = () => {
    const nextCode = inputCode.trim();
    if (nextCode) {
      setActiveCode(nextCode);
    }
  };

  if (!displayProfile) {
    return null;
  }

  return (
    <TooltipProvider>
      <Card className="overflow-hidden">
        <CardHeader className="space-y-4">
          <div className="space-y-2">
            <label className="text-xs font-medium text-slate-500" htmlFor="enterprise-stock-code">
              A股代码
            </label>
            <div className="flex gap-2">
              <div className="relative min-w-0 flex-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
                <Input
                  id="enterprise-stock-code"
                  value={inputCode}
                  onChange={(event) => setInputCode(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      handleSwitchCompany();
                    }
                  }}
                  className="h-9 pl-9"
                  inputMode="numeric"
                  placeholder="输入股票代码"
                />
              </div>
              <Button type="button" size="sm" variant="secondary" onClick={handleSwitchCompany}>
                切换
              </Button>
            </div>
            {!profile ? <p className="text-xs text-amber-600">未收录该代码，当前展示默认企业 600309。</p> : null}
          </div>

          <Separator />

          <div className="flex items-start gap-3">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-blue-100 bg-blue-50 text-sm font-semibold text-blue-700">
              {displayProfile.company.avatarLabel}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <h1 className="truncate text-base font-semibold leading-6 text-slate-950">{displayProfile.company.name}</h1>
                <Badge variant="slate">{displayProfile.stockCode}</Badge>
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
                <CompanyFact icon={Building2} label={displayProfile.company.industry} />
                <CompanyFact icon={CalendarDays} label={`${displayProfile.company.founded}成立`} />
                <CompanyFact icon={UsersRound} label={displayProfile.company.employees} />
              </div>
            </div>
          </div>
        </CardHeader>

        <Separator />

        <CardContent className="space-y-5 pt-5">
          <div className="grid grid-cols-2 gap-3">
            {displayProfile.metrics.map((metric) => (
              <MetricCard key={metric.id} metric={metric} />
            ))}
          </div>

          <Separator />

          <section className="space-y-3">
            <h2 className="text-sm font-semibold text-slate-950">企业标签</h2>
            <div className="flex flex-wrap gap-2">
              {displayProfile.tags.map((tag) => (
                <Badge key={tag.id} variant="blue">
                  {tag.label}
                </Badge>
              ))}
            </div>
          </section>

          <Separator />

          <section className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold text-slate-950">风险观察</h2>
              <Badge variant={displayProfile.stockCode === "600309" ? "amber" : "emerald"}>前端Mock</Badge>
            </div>
            <div className="space-y-3">
              {displayProfile.risks.map((risk) => (
                <RiskRow key={risk.id} risk={risk} />
              ))}
            </div>
          </section>
        </CardContent>
      </Card>
    </TooltipProvider>
  );
}

/* ─── CompanyFact (small enough to keep inline) ─── */

interface CompanyFactProps {
  icon: ComponentType<{ className?: string }>;
  label: string;
}

function CompanyFact({ icon: Icon, label }: CompanyFactProps) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <Icon className="h-3.5 w-3.5 text-slate-400" aria-hidden="true" />
      <span>{label}</span>
    </span>
  );
}
