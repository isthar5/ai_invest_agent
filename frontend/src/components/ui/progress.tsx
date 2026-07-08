import * as React from "react";
import { cn } from "@/lib/utils";

const Progress = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement> & { value: number }
>(({ className, value, ...props }, ref) => {
  const width = `${Math.max(0, Math.min(100, value))}%`;

  return (
    <div ref={ref} className={cn("relative h-2 w-full overflow-hidden rounded-full bg-slate-100", className)} {...props}>
      <div className="h-full bg-blue-600 transition-all" style={{ width }} />
    </div>
  );
});
Progress.displayName = "Progress";

export { Progress };
