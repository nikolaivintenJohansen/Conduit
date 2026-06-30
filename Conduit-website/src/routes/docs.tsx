import { createFileRoute, Link } from "@tanstack/react-router";
import { MarketingNav, MarketingFooter } from "@/components/marketing-nav";

export const Route = createFileRoute("/docs")({
  head: () => ({
    meta: [
      { title: "Docs — Conduit" },
      { name: "description", content: "Conduit API documentation: wallet, gateway, and OAuth." },
      { property: "og:title", content: "Conduit documentation" },
      { property: "og:description", content: "Wallet API, gateway, and OAuth references." },
    ],
  }),
  component: DocsPage,
});

function DocsPage() {
  const sections = [
    { t: "Wallet API", p: "/wallet/v1/*", d: "Funds, top-ups, keys, access groups, connected apps." },
    { t: "Gateway", p: "/v1/*", d: "OpenAI-compatible chat completions metered against the wallet." },
    { t: "OAuth", p: "/oauth/*", d: "Authorization, token exchange, JWKS, OpenID discovery." },
  ];
  return (
    <div className="bg-[var(--surface)] text-[var(--ink)]">
      <MarketingNav />
      <section className="mx-auto max-w-4xl px-6 pt-24 pb-16">
        <h1 className="text-5xl font-semibold tracking-[-0.03em]">Documentation</h1>
        <p className="mt-4 text-lg text-[var(--muted-foreground)]">
          Full OpenAPI specs ship with the backend at <code className="mono text-[var(--brand-primary)]">openapi/wallet-api.yaml</code> and
          <code className="mono text-[var(--brand-primary)]"> openapi/gateway.yaml</code>.
        </p>
      </section>
      <section className="mx-auto max-w-4xl px-6 pb-24 space-y-4">
        {sections.map((s) => (
          <div key={s.t} className="card-soft card-soft-hover p-6 flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold">{s.t}</h3>
              <p className="text-sm text-[var(--muted-foreground)]">{s.d}</p>
            </div>
            <code className="mono text-sm text-[var(--brand-primary)]">{s.p}</code>
          </div>
        ))}
        <div className="card-soft p-6 text-sm text-[var(--muted-foreground)]">
          Ready to start?{" "}
          <Link to="/auth" search={{ tab: "register" }} className="text-[var(--brand-primary)] font-medium hover:underline">
            Create your wallet
          </Link>{" "}
          and grab an API key from the dashboard.
        </div>
      </section>
      <MarketingFooter />
    </div>
  );
}
