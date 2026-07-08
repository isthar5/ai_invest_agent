import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface TooltipProviderProps {
  children: ReactNode;
}

interface TooltipProps {
  children: ReactNode;
}

interface TooltipTriggerProps {
  children: ReactNode;
  className?: string;
}

interface TooltipContentProps {
  children: ReactNode;
  className?: string;
}

export function TooltipProvider({ children }: TooltipProviderProps) {
  return <>{children}</>;
}

export function Tooltip({ children }: TooltipProps) {
  return <span className="group/tooltip relative inline-flex">{children}</span>;
}

export function TooltipTrigger({ children, className }: TooltipTriggerProps) {
  return <span className={cn("inline-flex cursor-default", className)}>{children}</span>;
}

export function TooltipContent({ children, className }: TooltipContentProps) {
  return (
    <span
      role="tooltip"
      className={cn(
        "pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 hidden w-56 -translate-x-1/2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs leading-5 text-slate-600 shadow-sm group-hover/tooltip:block group-focus-within/tooltip:block",
        className,
      )}
    >
      {children}
    </span>
  );
}