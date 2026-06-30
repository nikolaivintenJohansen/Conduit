import { cn } from "@/lib/utils";

export function Halo({ className }: { className?: string }) {
  return (
    <div className={cn("absolute inset-0 -z-10 overflow-hidden", className)} aria-hidden>
      <div className="halo halo-animated" />
    </div>
  );
}
