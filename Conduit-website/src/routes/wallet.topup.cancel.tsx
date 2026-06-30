import { createFileRoute, Link } from "@tanstack/react-router";
import { XCircle } from "lucide-react";
import { Button } from "@/components/ui-prim/button";
import { RingMark } from "@/components/ring-mark";

export const Route = createFileRoute("/wallet/topup/cancel")({
  head: () => ({ meta: [{ title: "Top-up canceled — Conduit" }] }),
  component: CancelPage,
});

function CancelPage() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-[var(--surface)] px-6 text-center">
      <RingMark size={40} />
      <XCircle className="h-12 w-12 text-[var(--muted-foreground)] mt-6" />
      <h1 className="mt-4 text-3xl font-semibold tracking-tight">Top-up canceled</h1>
      <p className="mt-2 text-[var(--muted-foreground)] max-w-md">No charges were made. You can try again any time.</p>
      <div className="mt-8 flex gap-2">
        <Link to="/dashboard">
          <Button size="lg">Back to dashboard</Button>
        </Link>
      </div>
    </div>
  );
}
