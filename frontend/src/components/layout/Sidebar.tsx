import type { ComponentType } from "react";
import { Building2, CircleDollarSign, ShieldCheck, Users } from "lucide-react";
import { SectionCard } from "@/components/ui/SectionCard";
import { SectionTitle } from "@/components/ui/SectionTitle";
import { EnterpriseProfileCard } from "@/components/enterprise/EnterpriseProfileCard";
import type { EnterpriseProfile } from "@/types/dashboard";

interface SidebarProps {
  enterprise: EnterpriseProfile;
}

export function Sidebar({ enterprise }: SidebarProps) {
  return (
    <aside className="flex h-full flex-col overflow-y-auto border-r border-slate-200 bg-slate-50 p-5">
      <div className="flex flex-col gap-4">
        <EnterpriseProfileCard enterprise={enterprise} />
        <SectionCard className="space-y-4">
          <SectionTitle title="企业信号" description="精选内部与公开指标，辅助判断企业状态。" />
          <div className="grid gap-3 text-sm">
            <Signal icon={ShieldCheck} label="合规状况" value="稳定" />
            <Signal icon={CircleDollarSign} label="资本活动" value="近期C轮融资" />
            <Signal icon={Users} label="招聘增速" value="同比+12%" />
            <Signal icon={Building2} label="供应商网络" value="Tier 1" />
          </div>
        </SectionCard>
      </div>
    </aside>
  );
}

interface SignalProps {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: string;
}

function Signal({ icon: Icon, label, value }: SignalProps) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2">
      <div className="flex min-w-0 items-center gap-2 text-slate-600">
        <Icon className="h-4 w-4 shrink-0 text-blue-600" />
        <span className="truncate">{label}</span>
      </div>
      <span className="shrink-0 font-medium text-slate-900">{value}</span>
    </div>
  );
}
