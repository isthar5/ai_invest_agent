import type { ReactNode } from "react";
import { Header } from "@/components/layout/Header";
import { RightPanel } from "@/components/layout/RightPanel";
import { Sidebar } from "@/components/layout/Sidebar";
import type { EnterpriseProfile, WorkflowNode } from "@/types/dashboard";

interface DashboardLayoutProps {
  children: ReactNode;
  enterprise: EnterpriseProfile;
  workflow: WorkflowNode[];
}

export function DashboardLayout({ children, enterprise, workflow }: DashboardLayoutProps) {
  return (
    <div className="flex h-screen flex-col overflow-hidden bg-slate-50 text-slate-950">
      <Header />
      <div className="grid flex-1 overflow-hidden laptop:grid-cols-[360px_1fr_400px] grid-cols-[320px_1fr_360px]">
        <Sidebar enterprise={enterprise} />
        <main className="overflow-hidden">{children}</main>
        <RightPanel workflow={workflow} />
      </div>
    </div>
  );
}
