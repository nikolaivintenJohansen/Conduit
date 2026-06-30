import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

type Variant = "default" | "primary" | "success" | "warning" | "danger" | "muted";

interface Props extends HTMLAttributes<HTMLSpanElement> {
  variant?: Variant;
}

const variants: Record<Variant, string> = {
  default: "bg-[var(--surface-alt)] text-[var(--ink)] border-[var(--hairline)]",
  primary: "bg-[#eaf2ff] text-[var(--brand-primary)] border-[#cfe1ff]",
  success: "bg-[#e6f7ee] text-[#0f7c4d] border-[#bce5cd]",
  warning: "bg-[#fff5e0] text-[#8a5a00] border-[#ffe0a3]",
  danger: "bg-[#fdecef] text-[#b3123c] border-[#f7c5d1]",
  muted: "bg-[var(--surface-alt)] text-[var(--muted-foreground)] border-[var(--hairline)]",
};

export function Badge({ className, variant = "default", ...rest }: Props) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium",
        variants[variant],
        className,
      )}
      {...rest}
    />
  );
}
