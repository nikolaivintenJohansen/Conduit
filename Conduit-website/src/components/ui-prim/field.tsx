import { forwardRef, type InputHTMLAttributes, useId } from "react";
import { cn } from "@/lib/utils";

interface FieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "prefix"> {
  label?: string;
  hint?: string;
  error?: string;
  prefix?: React.ReactNode;
  suffix?: React.ReactNode;
}

export const Field = forwardRef<HTMLInputElement, FieldProps>(
  ({ label, hint, error, prefix, suffix, className, id, ...rest }, ref) => {
    const auto = useId();
    const inputId = id ?? auto;
    return (
      <div className="space-y-1.5">
        {label && (
          <label htmlFor={inputId} className="text-sm font-medium text-[var(--ink)]">
            {label}
          </label>
        )}
        <div
          className={cn(
            "flex items-center rounded-lg border bg-white transition-shadow",
            error ? "border-[var(--destructive)]" : "border-[var(--hairline)] focus-within:border-[var(--brand-secondary)] focus-within:shadow-[0_0_0_3px_rgba(0,132,255,0.15)]",
          )}
        >
          {prefix && <span className="pl-3 text-sm text-[var(--muted-foreground)]">{prefix}</span>}
          <input
            ref={ref}
            id={inputId}
            className={cn(
              "h-11 flex-1 bg-transparent px-3 text-sm text-[var(--ink)] outline-none placeholder:text-[var(--muted-foreground)]",
              className,
            )}
            {...rest}
          />
          {suffix && <span className="pr-3 text-sm text-[var(--muted-foreground)]">{suffix}</span>}
        </div>
        {error ? (
          <p className="text-xs text-[var(--destructive)]">{error}</p>
        ) : hint ? (
          <p className="text-xs text-[var(--muted-foreground)]">{hint}</p>
        ) : null}
      </div>
    );
  },
);
Field.displayName = "Field";
