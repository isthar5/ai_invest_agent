import { Bell, Bot, Moon, Search } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function Header() {
  return (
    <header className="z-40 flex h-16 shrink-0 items-center border-b border-slate-200 bg-white px-6 shadow-sm">
      <div className="flex w-[320px] shrink-0 items-center gap-3 laptop:w-[360px]">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-blue-100 bg-blue-50 text-blue-700">
          <Bot className="h-5 w-5" aria-hidden="true" />
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-slate-950">企业智能分析平台</p>
          <p className="text-xs text-slate-500">企业分析工作台</p>
        </div>
      </div>

      <div className="mx-auto flex w-full max-w-[680px] items-center px-6 laptop:max-w-[760px]">
        <div className="relative w-full">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
          <Input className="h-9 pl-9" placeholder="搜索企业、工作流、分析报告..." readOnly />
        </div>
      </div>

      <div className="flex w-[360px] shrink-0 items-center justify-end gap-2 laptop:w-[400px]">
        <Button variant="ghost" size="icon" aria-label="切换主题">
          <Moon className="h-4 w-4" aria-hidden="true" />
        </Button>
        <Button variant="ghost" size="icon" aria-label="通知">
          <Bell className="h-4 w-4" aria-hidden="true" />
        </Button>
        <Avatar className="h-9 w-9 border border-slate-200">
          <AvatarFallback>AI</AvatarFallback>
        </Avatar>
      </div>
    </header>
  );
}
