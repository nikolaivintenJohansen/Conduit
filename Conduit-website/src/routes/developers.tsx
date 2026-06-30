import { createFileRoute, Link } from "@tanstack/react-router";
import { MarketingNav, MarketingFooter } from "@/components/marketing-nav";
import { Halo } from "@/components/halo";
import { Button } from "@/components/ui-prim/button";
import { DarkCodeBlock } from "@/components/ui-prim/dark-code-block";

export const Route = createFileRoute("/developers")({
  head: () => ({
    meta: [
      { title: "Developers — Conduit" },
      {
        name: "description",
        content:
          "Build on Conduit. Register an OAuth client, issue scoped API keys, monitor usage, and receive batch payouts via Stripe Connect.",
      },
      { property: "og:title", content: "Conduit for developers" },
      { property: "og:description", content: "OAuth + Stripe Connect payouts for AI apps." },
    ],
  }),
  component: DevelopersPage,
});

function DevelopersPage() {
  return (
    <div className="bg-[var(--surface)] text-[var(--ink)]">
      <MarketingNav />
      <section className="relative overflow-hidden">
        <Halo />
        <div className="mx-auto max-w-5xl px-6 pt-24 pb-16 text-center">
          <p className="text-sm font-medium text-[var(--brand-primary)] mb-3">For AI developers</p>
          <h1 className="text-5xl md:text-6xl font-semibold tracking-[-0.03em]">
            A drop-in billing layer for AI.
          </h1>
          <p className="mt-5 mx-auto max-w-2xl text-lg text-[var(--muted-foreground)]">
            Register your app, let users connect their Conduit wallet, and charge per token. We handle
            funds, allowances, refunds, and payouts.
          </p>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-6 py-16 grid md:grid-cols-2 gap-10 items-start">
        <div>
          <h2 className="text-3xl font-semibold tracking-tight mb-4">1. Add the Connect button</h2>
          <p className="text-[var(--muted-foreground)] mb-6">
            Send users to the Conduit OAuth consent screen. They approve a spend cap, you receive a code,
            exchange it for tokens, and start charging.
          </p>
          <DarkCodeBlock
            language="html"
            code={`<a href="https://conduit.app/oauth/consent
  ?client_id=app_live_..._abc
  &redirect_uri=https://yourapp.com/cb
  &response_type=code
  &scope=wallet:charge profile:read
  &state=xyz
  &code_challenge=...
  &code_challenge_method=S256">
  Connect AI Wallet
</a>`}
          />
        </div>
        <div>
          <h2 className="text-3xl font-semibold tracking-tight mb-4">2. Charge per request</h2>
          <p className="text-[var(--muted-foreground)] mb-6">
            Use the Conduit gateway as a drop-in OpenAI-compatible endpoint. We meter tokens and debit
            the user's wallet.
          </p>
          <DarkCodeBlock
            language="bash"
            code={`curl https://api.conduit.dev/v1/chat/completions \\
  -H "Authorization: Bearer sk-uaw-..." \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role":"user","content":"hello"}]
  }'`}
          />
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-6 py-16">
        <div className="card-soft p-10 text-center">
          <h2 className="text-3xl font-semibold tracking-tight">Get paid via Stripe Connect.</h2>
          <p className="mt-3 max-w-xl mx-auto text-[var(--muted-foreground)]">
            Conduit handles aggregation and net-of-fees settlement to your Stripe Connect account on a
            rolling schedule.
          </p>
          <div className="mt-6">
            <Link to="/auth" search={{ tab: "register" }}>
              <Button size="lg">Get started</Button>
            </Link>
          </div>
        </div>
      </section>

      <MarketingFooter />
    </div>
  );
}
