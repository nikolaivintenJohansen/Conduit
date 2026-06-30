import { createFileRoute, Link } from "@tanstack/react-router";
import { MarketingNav, MarketingFooter } from "@/components/marketing-nav";
import { Button } from "@/components/ui-prim/button";
import { Check } from "lucide-react";

export const Route = createFileRoute("/pricing")({
  head: () => ({
    meta: [
      { title: "Pricing — Conduit" },
      {
        name: "description",
        content: "Pay only for what you use. No subscriptions, no minimums. Prepaid micro-charging in USD.",
      },
      { property: "og:title", content: "Conduit pricing" },
      { property: "og:description", content: "Prepaid, per-token, no subscriptions." },
    ],
  }),
  component: PricingPage,
});

function PricingPage() {
  return (
    <div className="bg-[var(--surface)] text-[var(--ink)]">
      <MarketingNav />
      <section className="mx-auto max-w-5xl px-6 pt-24 pb-12 text-center">
        <h1 className="text-5xl md:text-6xl font-semibold tracking-[-0.03em]">Pay per token. Period.</h1>
        <p className="mt-5 mx-auto max-w-xl text-lg text-[var(--muted-foreground)]">
          No subscriptions. No seats. Add funds whenever, spend whenever, withdraw the unused balance.
        </p>
      </section>
      <section className="mx-auto max-w-5xl px-6 pb-24 grid md:grid-cols-2 gap-6">
        <div className="card-soft p-8">
          <div className="text-sm text-[var(--brand-primary)] font-medium mb-2">For users</div>
          <div className="mono text-4xl font-semibold mb-1">Free wallet</div>
          <p className="text-sm text-[var(--muted-foreground)] mb-6">
            Top up any amount ≥ $0.50. You pay model providers' published rates.
          </p>
          <ul className="space-y-2 text-sm">
            {["Per-app spend caps", "Cursor-paginated history", "Stripe-backed top-ups", "Revoke any app instantly"].map(
              (b) => (
                <li key={b} className="flex items-center gap-2">
                  <Check className="h-4 w-4 text-[var(--brand-primary)]" /> {b}
                </li>
              ),
            )}
          </ul>
          <div className="mt-8">
            <Link to="/auth" search={{ tab: "register" }}>
              <Button>Create wallet</Button>
            </Link>
          </div>
        </div>
        <div className="card-soft p-8 border-[var(--brand-primary)]">
          <div className="text-sm text-[var(--brand-primary)] font-medium mb-2">For AI apps</div>
          <div className="mono text-4xl font-semibold mb-1">2.5% + 30¢</div>
          <p className="text-sm text-[var(--muted-foreground)] mb-6">
            Per settlement. We aggregate user charges and pay you via Stripe Connect.
          </p>
          <ul className="space-y-2 text-sm">
            {["OAuth 2.1 + PKCE", "Per-app rate limits", "Webhook event delivery", "Rotating secrets"].map((b) => (
              <li key={b} className="flex items-center gap-2">
                <Check className="h-4 w-4 text-[var(--brand-primary)]" /> {b}
              </li>
            ))}
          </ul>
          <div className="mt-8">
            <Link to="/developers">
              <Button variant="dark">Become a partner</Button>
            </Link>
          </div>
        </div>
      </section>
      <MarketingFooter />
    </div>
  );
}
