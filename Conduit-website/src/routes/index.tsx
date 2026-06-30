import { createFileRoute, Link } from "@tanstack/react-router";
import { Wallet, Plug, Zap, Shield, Gauge, KeyRound, ArrowRight, Check } from "lucide-react";
import { MarketingNav, MarketingFooter } from "@/components/marketing-nav";
import { Halo } from "@/components/halo";
import { Button } from "@/components/ui-prim/button";
import { RingMark } from "@/components/ring-mark";
import { DarkCodeBlock } from "@/components/ui-prim/dark-code-block";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Conduit — One wallet. Every AI app." },
      {
        name: "description",
        content:
          "Fund one prepaid balance, then connect it to coding assistants, image generators, writing tools and more. Per-app spend caps, prepaid micro-charging, Stripe-backed security.",
      },
      { property: "og:title", content: "Conduit — One wallet. Every AI app." },
      {
        property: "og:description",
        content: "MetaMask for AI. One balance, many apps, per-token billing.",
      },
    ],
  }),
  component: HomePage,
});

function HomePage() {
  return (
    <div className="bg-[var(--surface)] text-[var(--ink)]">
      <MarketingNav />
      <Hero />
      <LogoWall />
      <HowItWorks />
      <ProductSection
        eyebrow="Spend controls"
        title="Hard caps on every app."
        body="Set a monthly or lifetime spend limit on each connected app. Revoke instantly with one click. Runaway AI agents stop at the wallet, not at your credit card."
        bullets={["Per-app spend caps", "Live allowance progress", "One-click revoke"]}
        flip
      />
      <ProductSection
        eyebrow="Developers"
        title="One key, every model."
        body="Issue API keys scoped to access groups — bundles of models that key is allowed to call. Rotate without redeploys. Monitor spend in real time."
        bullets={["Per-key rate limits", "Access groups gate model use", "Cursor-paginated usage logs"]}
        codeExample
      />
      <StatsBand />
      <ForPartners />
      <CtaBand />
      <MarketingFooter />
    </div>
  );
}

function Hero() {
  return (
    <section className="relative overflow-hidden">
      <Halo />
      <div className="mx-auto max-w-7xl px-6 pt-20 pb-28 md:pt-32 md:pb-36 text-center">
        <div className="inline-flex items-center gap-2 rounded-full border border-[var(--hairline)] bg-white px-3 py-1 text-xs font-medium text-[var(--muted-foreground)] mb-6">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--brand-secondary)]" />
          Prepaid · Per-token · Universal
        </div>
        <h1 className="mx-auto max-w-4xl text-5xl md:text-7xl font-semibold tracking-[-0.03em] leading-[1.05]">
          One wallet. <span className="text-gradient-brand">Every AI app.</span>
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg text-[var(--muted-foreground)] leading-relaxed">
          Conduit is the universal prepaid wallet for the AI ecosystem. Fund once, connect any AI app, and
          pay only for the tokens you actually use — no more fragmented subscriptions.
        </p>
        <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
          <Link to="/auth" search={{ tab: "register" }}>
            <Button size="lg" variant="primary">
              Sign up free <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
          <Link to="/developers">
            <Button size="lg" variant="secondary">
              For AI apps & developers
            </Button>
          </Link>
        </div>

        <div className="relative mx-auto mt-16 max-w-4xl">
          <BalanceMock />
        </div>
      </div>
    </section>
  );
}

function BalanceMock() {
  return (
    <div className="relative">
      <div className="absolute -inset-4 -z-10 bg-gradient-brand opacity-20 blur-3xl rounded-3xl" />
      <div className="rounded-2xl border border-[var(--hairline)] bg-white shadow-[0_30px_90px_-30px_rgba(0,97,213,0.35)] overflow-hidden text-left">
        <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--hairline)] bg-[var(--surface-alt)]">
          <div className="flex items-center gap-2">
            <RingMark size={20} />
            <span className="text-sm font-semibold">Wallet</span>
          </div>
          <span className="text-xs text-[var(--muted-foreground)]">conduit.app/dashboard</span>
        </div>
        <div className="p-8">
          <div className="text-xs uppercase tracking-wider text-[var(--muted-foreground)]">Balance</div>
          <div className="mt-2 mono text-5xl font-semibold tracking-tight text-[var(--ink)]">
            $124.<span className="text-[var(--muted-foreground)]">38</span>
          </div>
          <div className="mt-1 text-sm text-[var(--muted-foreground)]">
            Available <span className="mono">$118.04</span> · Held <span className="mono">$6.34</span>
          </div>
          <div className="mt-6 grid grid-cols-3 gap-4">
            {[
              { name: "GPT Coder", spent: 42, cap: 50 },
              { name: "Pixel Studio", spent: 8, cap: 25 },
              { name: "DocDraft AI", spent: 3, cap: 10 },
            ].map((app) => (
              <div key={app.name} className="rounded-lg border border-[var(--hairline)] p-3 bg-[var(--surface-alt)]">
                <div className="text-xs font-medium text-[var(--ink)]">{app.name}</div>
                <div className="mt-2 h-1.5 w-full rounded-full bg-white overflow-hidden">
                  <div
                    className="h-full bg-gradient-brand"
                    style={{ width: `${(app.spent / app.cap) * 100}%` }}
                  />
                </div>
                <div className="mt-1.5 mono text-[11px] text-[var(--muted-foreground)]">
                  ${app.spent}.00 / ${app.cap}.00
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function LogoWall() {
  const apps = ["GPTCoder", "PixelStudio", "DocDraft", "MuseAI", "Verbatim", "CodexCloud"];
  return (
    <section className="border-y border-[var(--hairline)] bg-[var(--surface-alt)] py-10">
      <div className="mx-auto max-w-7xl px-6">
        <p className="text-center text-xs uppercase tracking-widest text-[var(--muted-foreground)] mb-6">
          Trusted by AI apps everywhere
        </p>
        <div className="flex flex-wrap items-center justify-center gap-x-12 gap-y-4 opacity-60">
          {apps.map((a) => (
            <span key={a} className="text-lg font-semibold tracking-tight text-[var(--ink)]">
              {a}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}

function HowItWorks() {
  const steps = [
    {
      icon: Wallet,
      title: "Fund",
      desc: "Top up your Conduit wallet with any amount. Funds sit there as prepaid credit.",
    },
    {
      icon: Plug,
      title: "Connect",
      desc: "Click 'Connect AI Wallet' in any partner app and set a spending cap.",
    },
    {
      icon: Zap,
      title: "Use",
      desc: "Apps charge tiny per-token amounts against your balance. One bill, full visibility.",
    },
  ];
  return (
    <section className="mx-auto max-w-7xl px-6 py-24">
      <div className="text-center mb-14">
        <p className="text-sm font-medium text-[var(--brand-primary)] mb-2">How it works</p>
        <h2 className="text-4xl md:text-5xl font-semibold tracking-tight">Three steps to AI without subscriptions.</h2>
      </div>
      <div className="grid md:grid-cols-3 gap-6">
        {steps.map((s, i) => (
          <div key={s.title} className="card-soft card-soft-hover p-8">
            <div className="flex items-center gap-3 mb-4">
              <div className="h-10 w-10 rounded-xl bg-gradient-brand flex items-center justify-center text-white">
                <s.icon className="h-5 w-5" />
              </div>
              <span className="mono text-xs text-[var(--muted-foreground)]">0{i + 1}</span>
            </div>
            <h3 className="text-xl font-semibold mb-2">{s.title}</h3>
            <p className="text-sm text-[var(--muted-foreground)] leading-relaxed">{s.desc}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function ProductSection({
  eyebrow,
  title,
  body,
  bullets,
  flip,
  codeExample,
}: {
  eyebrow: string;
  title: string;
  body: string;
  bullets: string[];
  flip?: boolean;
  codeExample?: boolean;
}) {
  return (
    <section className="mx-auto max-w-7xl px-6 py-24">
      <div className={`grid md:grid-cols-2 gap-12 items-center ${flip ? "md:[&>*:first-child]:order-2" : ""}`}>
        <div>
          <p className="text-sm font-medium text-[var(--brand-primary)] mb-2">{eyebrow}</p>
          <h2 className="text-4xl font-semibold tracking-tight mb-4">{title}</h2>
          <p className="text-base text-[var(--muted-foreground)] leading-relaxed mb-6">{body}</p>
          <ul className="space-y-2.5">
            {bullets.map((b) => (
              <li key={b} className="flex items-center gap-2 text-sm">
                <Check className="h-4 w-4 text-[var(--brand-primary)]" />
                {b}
              </li>
            ))}
          </ul>
        </div>
        <div>
          {codeExample ? (
            <DarkCodeBlock
              language="bash"
              code={`curl https://api.conduit.dev/v1/chat/completions \\
  -H "Authorization: Bearer sk-conduit-..." \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role":"user","content":"hi"}]
  }'`}
            />
          ) : (
            <SpendControlsMock />
          )}
        </div>
      </div>
    </section>
  );
}

function SpendControlsMock() {
  return (
    <div className="card-soft p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="text-sm font-semibold">Connected apps</div>
        <span className="text-xs text-[var(--muted-foreground)]">3 active</span>
      </div>
      <div className="space-y-3">
        {[
          { n: "GPT Coder", c: "#0061D5", v: 0.84 },
          { n: "Pixel Studio", c: "#0084FF", v: 0.32 },
          { n: "DocDraft AI", c: "#0061D5", v: 0.18 },
        ].map((a) => (
          <div key={a.n} className="border border-[var(--hairline)] rounded-lg p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium">{a.n}</span>
              <span className="mono text-xs text-[var(--muted-foreground)]">monthly</span>
            </div>
            <div className="h-1.5 w-full rounded-full bg-[var(--surface-alt)] overflow-hidden">
              <div className="h-full bg-gradient-brand" style={{ width: `${a.v * 100}%` }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function StatsBand() {
  const stats = [
    { v: "1¢", l: "Minimum micro-charge" },
    { v: "<50ms", l: "Gateway p99 latency" },
    { v: "100%", l: "Stripe-backed funds" },
  ];
  return (
    <section className="bg-[var(--ink-dark)] text-white">
      <div className="mx-auto max-w-7xl px-6 py-20 grid md:grid-cols-3 gap-8 text-center">
        {stats.map((s) => (
          <div key={s.l}>
            <div className="mono text-5xl font-semibold tracking-tight text-gradient-brand">{s.v}</div>
            <div className="mt-2 text-sm text-[#8fa3c1]">{s.l}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function ForPartners() {
  return (
    <section className="mx-auto max-w-7xl px-6 py-24">
      <div className="card-soft p-12 relative overflow-hidden">
        <div className="absolute -top-20 -right-20 h-72 w-72 rounded-full bg-gradient-brand opacity-20 blur-3xl" />
        <div className="relative grid md:grid-cols-2 gap-12 items-center">
          <div>
            <p className="text-sm font-medium text-[var(--brand-primary)] mb-2">For AI app makers</p>
            <h2 className="text-4xl font-semibold tracking-tight mb-4">
              Stop building billing. Ship product.
            </h2>
            <p className="text-base text-[var(--muted-foreground)] leading-relaxed mb-6">
              Register your app as a Conduit OAuth client. Your users click "Connect AI Wallet" and grant a
              spend cap. We bill them, you get paid via Stripe Connect.
            </p>
            <Link to="/developers">
              <Button variant="dark">
                Become a partner <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
          </div>
          <div className="grid grid-cols-2 gap-4">
            {[
              { i: Shield, t: "OAuth 2.1 + PKCE" },
              { i: Gauge, t: "Per-app rate limits" },
              { i: KeyRound, t: "Rotate secrets anytime" },
              { i: Wallet, t: "Stripe Connect payouts" },
            ].map((f) => (
              <div key={f.t} className="border border-[var(--hairline)] rounded-lg p-4 bg-white">
                <f.i className="h-5 w-5 text-[var(--brand-primary)] mb-2" />
                <div className="text-sm font-medium">{f.t}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function CtaBand() {
  return (
    <section className="relative overflow-hidden">
      <div className="absolute inset-0 -z-10">
        <div className="halo halo-animated" />
      </div>
      <div className="mx-auto max-w-3xl px-6 py-24 text-center">
        <h2 className="text-4xl md:text-5xl font-semibold tracking-tight">
          One balance. One bill. Every AI.
        </h2>
        <p className="mt-4 text-lg text-[var(--muted-foreground)]">
          Start with $5. Use any connected app. Stop anytime.
        </p>
        <div className="mt-8 flex items-center justify-center gap-3">
          <Link to="/auth" search={{ tab: "register" }}>
            <Button size="lg">Create your wallet</Button>
          </Link>
          <Link to="/developers">
            <Button size="lg" variant="secondary">
              For developers
            </Button>
          </Link>
        </div>
      </div>
    </section>
  );
}
