import { CopyButton } from "./copy-button";
import { cn } from "@/lib/utils";

export function DarkCodeBlock({
  code,
  language,
  className,
}: {
  code: string;
  language?: string;
  className?: string;
}) {
  return (
    <div className={cn("relative rounded-xl bg-[var(--ink-dark)] text-[#dce8ff] overflow-hidden", className)}>
      {language && (
        <div className="px-4 py-2 border-b border-white/10 text-[11px] uppercase tracking-widest text-[#8fa3c1]">
          {language}
        </div>
      )}
      <div className="absolute top-2 right-2">
        <CopyButton value={code} className="bg-white/10 border-white/15 text-white hover:bg-white/15" />
      </div>
      <pre className="px-4 py-4 mono text-[13px] leading-relaxed overflow-x-auto">{code}</pre>
    </div>
  );
}
