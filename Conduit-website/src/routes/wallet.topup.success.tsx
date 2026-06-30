import { createFileRoute, Link } from "@tanstack/react-router";
import { CheckCircle2 } from "lucide-react";
import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui-prim/button";
import { RingMark } from "@/components/ring-mark";

export const Route = createFileRoute("/wallet/topup/success")({
  head: () => ({ meta: [{ title: "Top-up complete — Conduit" }] }),
  component: SuccessPage,
});

function SuccessPage() {
  const qc = useQueryClient();
  useEffect(() => {
    qc.invalidateQueries({ queryKey: ["me"] });
    qc.invalidateQueries({ queryKey: ["wallet"] });
    qc.invalidateQueries({ queryKey: ["transactions"] });
  }, [qc]);
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-[var(--surface)] px-6 text-center">
      <RingMark size={40} />
      <CheckCircle2 className="h-12 w-12 text-[#0f7c4d] mt-6" />
      <h1 className="mt-4 text-3xl font-semibold tracking-tight">Funds added</h1>
      <p className="mt-2 text-[var(--muted-foreground)] max-w-md">
        Your wallet has been topped up. It may take a few seconds to appear.
      </p>
      <div className="mt-8">
        <Link to="/dashboard">
          <Button size="lg">Back to dashboard</Button>
        </Link>
      </div>
    </div>
  );
}
