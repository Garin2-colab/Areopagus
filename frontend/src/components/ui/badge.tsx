import * as React from "react";

import { cn } from "@/lib/utils";

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {}

export function Badge({ className, ...props }: BadgeProps) {
  return <div className={cn("inline-flex items-center border border-zinc-700 px-2 py-1 text-xs text-zinc-300", className)} {...props} />;
}
