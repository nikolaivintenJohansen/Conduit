import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "dark" | "danger";
type Size = "sm" | "md" | "lg";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
}

const base =
  "inline-flex items-center justify-center gap-2 rounded-full font-medium transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-secondary)] focus-visible:ring-offset-2 whitespace-nowrap";

const variants: Record<Variant, string> = {
  primary:
    "bg-[var(--brand-primary)] text-white hover:bg-[var(--brand-secondary)] shadow-[0_2px_6px_rgba(0,97,213,0.25)] hover:shadow-[0_6px_18px_-4px_rgba(0,132,255,0.45)] active:translate-y-px",
  secondary:
    "bg-white text-[var(--ink)] border border-[var(--hairline)] hover:border-[var(--brand-secondary)] hover:text-[var(--brand-primary)]",
  ghost: "text-[var(--ink)] hover:bg-[var(--surface-alt)]",
  dark: "bg-[var(--ink)] text-white hover:bg-[#11315b]",
  danger: "bg-[var(--destructive)] text-white hover:opacity-90",
};

const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-sm",
  md: "h-10 px-5 text-sm",
  lg: "h-12 px-7 text-base",
};

export const Button = forwardRef<HTMLButtonElement, Props>(
  ({ className, variant = "primary", size = "md", loading, children, disabled, ...rest }, ref) => (
    <button
      ref={ref}
      className={cn(base, variants[variant], sizes[size], className)}
      disabled={disabled || loading}
      {...rest}
    >
      {loading && (
        <span
          className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"
          aria-hidden
        />
      )}
      {children}
    </button>
  ),
);
Button.displayName = "Button";
