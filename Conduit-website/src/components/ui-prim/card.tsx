import { forwardRef, type HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface Props extends HTMLAttributes<HTMLDivElement> {
  hoverable?: boolean;
  padding?: "sm" | "md" | "lg" | "none";
}

const pad = {
  none: "",
  sm: "p-4",
  md: "p-6",
  lg: "p-8",
};

export const Card = forwardRef<HTMLDivElement, Props>(
  ({ className, hoverable, padding = "md", ...rest }, ref) => (
    <div
      ref={ref}
      className={cn("card-soft", hoverable && "card-soft-hover", pad[padding], className)}
      {...rest}
    />
  ),
);
Card.displayName = "Card";

export function CardHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 mb-5">
      <div>
        <h3 className="text-base font-semibold text-[var(--ink)] tracking-tight">{title}</h3>
        {subtitle && <p className="mt-1 text-sm text-[var(--muted-foreground)]">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}
