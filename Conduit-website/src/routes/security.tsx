import { createFileRoute } from "@tanstack/react-router";
import { MarketingNav, MarketingFooter } from "@/components/marketing-nav";
import { Shield, Lock, KeyRound, FileCheck } from "lucide-react";

export const Route = createFileRoute("/security")({
  head: () => ({
    meta: [
      { title: "Security — Conduit" },
      {
        name: "description",
        content: "How Conduit protects your funds, keys, and identity. Stripe-backed funds, OAuth 2.1 + PKCE, scoped API keys.",
      },
      { property: "og:title", content: "Conduit security" },
      { property: "og:description", content: "Stripe-backed funds. OAuth 2.1. Scoped keys. Per-app caps." },
    ],
  }),
  component: SecurityPage,
});

function SecurityPage() {
  const items = [
    { i: Shield, t: "Stripe-backed funds", d: "All top-ups settle through Stripe. We never touch raw card data." },
    { i: Lock, t: "Per-app spend caps", d: "Hard ceilings stop runaway agents at the wallet, before charges land." },
    { i: KeyRound, t: "Scoped API keys", d: "Each key is gated to a named access group of models, with rate limits." },
    { i: FileCheck, t: "Audit-ready ledger", d: "Every debit, credit, refund, and settlement recorded with request IDs." },
  ];
  return (
    <div className="bg-[var(--surface)] text-[var(--ink)]">
      <MarketingNav />
      <section className="mx-auto max-w-4xl px-6 pt-24 pb-16 text-center">
        <h1 className="text-5xl md:text-6xl font-semibold tracking-[-0.03em]">Security you can audit.</h1>
        <p className="mt-5 mx-auto max-w-2xl text-lg text-[var(--muted-foreground)]">
          Conduit is built on the same primitives banks and fintechs use to move billions safely — applied
          to micro-transactions for AI.
        </p>
      </section>
      <section className="mx-auto max-w-5xl px-6 pb-24 grid md:grid-cols-2 gap-6">
        {items.map((it) => (
          <div key={it.t} className="card-soft p-8">
            <div className="h-10 w-10 rounded-xl bg-gradient-brand flex items-center justify-center text-white mb-4">
              <it.i className="h-5 w-5" />
            </div>
            <h3 className="text-lg font-semibold mb-1">{it.t}</h3>
            <p className="text-sm text-[var(--muted-foreground)]">{it.d}</p>
          </div>
        ))}
      </section>
      <MarketingFooter />
    </div>
  );
}
