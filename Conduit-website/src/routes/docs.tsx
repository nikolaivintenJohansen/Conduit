import { createFileRoute, Link } from "@tanstack/react-router";
import { MarketingNav, MarketingFooter } from "@/components/marketing-nav";
import { useState, useEffect, useCallback, type ReactNode } from "react";

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

/* ------------------------------------------------------------------ */
/*  Section keys                                                       */
/* ------------------------------------------------------------------ */
type Section =
  | "introduction"
  | "quickstart"
  | "authentication"
  | "api-reference"
  | "wallet-api"
  | "gateway-api"
  | "oauth"
  | "guide-ai-app"
  | "guide-spending-caps"
  | "guide-access-groups";

const SECTIONS: { key: Section; label: string; group: string }[] = [
  { key: "introduction", label: "Introduction", group: "Getting Started" },
  { key: "quickstart", label: "Quickstart", group: "Getting Started" },
  { key: "authentication", label: "Authentication", group: "Getting Started" },
  { key: "api-reference", label: "API Reference", group: "API Reference" },
  { key: "wallet-api", label: "Wallet API", group: "API Reference" },
  { key: "gateway-api", label: "Gateway API", group: "API Reference" },
  { key: "oauth", label: "OAuth 2.1", group: "API Reference" },
  { key: "guide-ai-app", label: "Building an AI App", group: "Guides" },
  { key: "guide-spending-caps", label: "Managing Spending Caps", group: "Guides" },
  { key: "guide-access-groups", label: "Access Groups", group: "Guides" },
];

/* ------------------------------------------------------------------ */
/*  Small reusable bits                                                */
/* ------------------------------------------------------------------ */
function Code({ children }: { children: ReactNode }) {
  return (
    <code className="mono text-[var(--brand-primary)] bg-[#eaf2ff] px-1.5 py-0.5 rounded text-[13px]">
      {children}
    </code>
  );
}

function CodeBlock({ title, lang, children }: { title?: string; lang?: string; children: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(children);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="relative group rounded-xl border border-[var(--hairline)] bg-[#0a1f3d] text-[#e2e8f0] overflow-hidden my-4">
      {title && (
        <div className="px-4 py-2 border-b border-white/10 text-xs text-[#8fa3c1] flex items-center justify-between">
          <span>{title}</span>
          <span className="text-[10px] uppercase tracking-wider opacity-60">{lang}</span>
        </div>
      )}
      <button
        onClick={copy}
        className="absolute top-2 right-2 px-2 py-1 text-[10px] uppercase tracking-wider rounded bg-white/10 text-white/60 hover:bg-white/20 hover:text-white transition-colors opacity-0 group-hover:opacity-100"
      >
        {copied ? "Copied!" : "Copy"}
      </button>
      <pre className="p-4 overflow-x-auto text-[13px] leading-relaxed mono">
        <code>{children}</code>
      </pre>
    </div>
  );
}

function Endpoint({ method, path, description }: { method: string; path: string; description: string }) {
  const colors: Record<string, string> = {
    GET: "bg-emerald-100 text-emerald-700",
    POST: "bg-blue-100 text-blue-700",
    PATCH: "bg-amber-100 text-amber-700",
    DELETE: "bg-red-100 text-red-700",
    PUT: "bg-purple-100 text-purple-700",
  };
  return (
    <div className="flex items-start gap-3 py-3 border-b border-[var(--hairline)] last:border-b-0">
      <span className={`shrink-0 px-2 py-0.5 rounded text-[11px] font-bold uppercase tracking-wider ${colors[method] || "bg-gray-100 text-gray-600"}`}>
        {method}
      </span>
      <div className="min-w-0">
        <code className="mono text-sm font-medium text-[var(--ink)]">{path}</code>
        <p className="text-sm text-[var(--muted-foreground)] mt-0.5 m-0">{description}</p>
      </div>
    </div>
  );
}

function ParamTable({ rows }: { rows: { name: string; type: string; req?: boolean; desc: string }[] }) {
  return (
    <div className="overflow-x-auto my-4">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="border-b border-[var(--hairline)]">
            <th className="text-left py-2 pr-4 font-semibold text-[var(--ink)]">Parameter</th>
            <th className="text-left py-2 pr-4 font-semibold text-[var(--ink)]">Type</th>
            <th className="text-left py-2 pr-4 font-semibold text-[var(--ink)]">Required</th>
            <th className="text-left py-2 font-semibold text-[var(--ink)]">Description</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-[var(--hairline)] last:border-b-0">
              <td className="py-2 pr-4"><Code>{r.name}</Code></td>
              <td className="py-2 pr-4 text-[var(--muted-foreground)] mono text-xs">{r.type}</td>
              <td className="py-2 pr-4">{r.req ? <span className="text-xs text-red-500 font-medium">Required</span> : <span className="text-xs text-[var(--muted-foreground)]">Optional</span>}</td>
              <td className="py-2 text-[var(--muted-foreground)]">{r.desc}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Callout({ type = "info", children }: { type?: "info" | "warning" | "tip"; children: ReactNode }) {
  const styles = {
    info: "bg-blue-50 border-blue-200 text-blue-800",
    warning: "bg-amber-50 border-amber-200 text-amber-800",
    tip: "bg-emerald-50 border-emerald-200 text-emerald-800",
  };
  const icons = { info: "💡", warning: "⚠️", tip: "✅" };
  return (
    <div className={`flex gap-3 p-4 rounded-xl border text-sm leading-relaxed my-4 ${styles[type]}`}>
      <span className="shrink-0 text-base">{icons[type]}</span>
      <div>{children}</div>
    </div>
  );
}

function SectionHeading({ children }: { children: ReactNode }) {
  return <h1 className="text-4xl font-semibold tracking-tight mb-4">{children}</h1>;
}

function SubHeading({ children, id }: { children: ReactNode; id?: string }) {
  return <h2 id={id} className="text-2xl font-semibold tracking-tight mt-10 mb-4">{children}</h2>;
}

function H3({ children }: { children: ReactNode }) {
  return <h3 className="text-lg font-semibold tracking-tight mt-8 mb-3">{children}</h3>;
}

function Prose({ children }: { children: ReactNode }) {
  return <div className="prose-conduit text-[15px] leading-relaxed text-[var(--muted-foreground)] space-y-4">{children}</div>;
}

/* ------------------------------------------------------------------ */
/*  Section content components                                         */
/* ------------------------------------------------------------------ */

function IntroductionSection({ nav }: { nav: (s: Section) => void }) {
  return (
    <>
      <SectionHeading>Documentation</SectionHeading>
      <Prose>
        <p>
          Conduit is the universal prepaid wallet for the AI ecosystem. One identity, one balance, every AI app.
          Learn how to integrate the wallet, manage API keys, and build apps that charge by the token.
        </p>
      </Prose>

      <SubHeading>API Specifications</SubHeading>
      <p className="text-sm text-[var(--muted-foreground)] mb-6">
        Full OpenAPI specs ship with the backend repository at <Code>openapi/wallet-api.yaml</Code> and <Code>openapi/gateway.yaml</Code>.
      </p>

      <div className="grid sm:grid-cols-2 gap-4">
        <button onClick={() => nav("wallet-api")} className="card-soft card-soft-hover p-6 text-left">
          <h3 className="text-base font-semibold mb-2">Wallet API</h3>
          <p className="text-sm text-[var(--muted-foreground)] mb-4">Funds, top-ups, API keys, access groups, connected apps.</p>
          <code className="mono text-[13px] font-medium text-[var(--ink)]">/wallet/v1/*</code>
        </button>
        <button onClick={() => nav("gateway-api")} className="card-soft card-soft-hover p-6 text-left">
          <h3 className="text-base font-semibold mb-2">Gateway</h3>
          <p className="text-sm text-[var(--muted-foreground)] mb-4">OpenAI-compatible chat completions metered against the wallet.</p>
          <code className="mono text-[13px] font-medium text-[var(--ink)]">/v1/*</code>
        </button>
        <button onClick={() => nav("oauth")} className="card-soft card-soft-hover p-6 sm:col-span-2 text-left">
          <h3 className="text-base font-semibold mb-2">OAuth</h3>
          <p className="text-sm text-[var(--muted-foreground)] mb-4">Authorization, token exchange, JWKS, OpenID discovery endpoints.</p>
          <code className="mono text-[13px] font-medium text-[var(--ink)]">/oauth/*</code>
        </button>
      </div>

      <div className="border-t border-[var(--hairline)] pt-12 mt-12">
        <SubHeading>Ready to start?</SubHeading>
        <div className="card-soft p-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <p className="text-sm text-[var(--muted-foreground)] m-0">
            Create your free wallet, grab an API key, and make your first request in seconds.
          </p>
          <Link to="/auth" search={{ tab: "register" }} className="shrink-0 inline-flex items-center justify-center rounded-full bg-[var(--brand-primary)] px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[var(--brand-secondary)]">
            Create wallet
          </Link>
        </div>
      </div>
    </>
  );
}

function QuickstartSection() {
  return (
    <>
      <SectionHeading>Quickstart</SectionHeading>
      <Prose>
        <p>
          Get from zero to your first metered AI request in under five minutes. You'll create a wallet, generate a virtual API key, and send a chat completion through the Conduit gateway.
        </p>
      </Prose>

      <SubHeading>1. Create your wallet</SubHeading>
      <Prose>
        <p>Sign up at <Link to="/auth" search={{ tab: "register" }} className="text-[var(--brand-primary)] font-medium hover:underline">conduit.ai/auth</Link> or register via the API:</p>
      </Prose>
      <CodeBlock title="Register a new account" lang="bash">{`curl -X POST https://api.conduit.ai/wallet/v1/auth/register \\
  -H "Content-Type: application/json" \\
  -d '{
    "email": "you@example.com",
    "password": "your-secure-password"
  }'`}</CodeBlock>
      <Prose>
        <p>The response includes a JWT <Code>access_token</Code> you'll use for all subsequent wallet operations.</p>
      </Prose>
      <CodeBlock title="Response" lang="json">{`{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "you@example.com"
  }
}`}</CodeBlock>

      <SubHeading>2. Fund your wallet</SubHeading>
      <Prose>
        <p>Add funds via Stripe Checkout. The minimum top-up is $0.50 (500,000 microdollars).</p>
      </Prose>
      <CodeBlock title="Create a top-up checkout session" lang="bash">{`curl -X POST https://api.conduit.ai/wallet/v1/topups/checkout \\
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{ "amount_microdollars": 10000000 }'`}</CodeBlock>
      <Callout type="info">
        All monetary values in Conduit are <strong>integer microdollars</strong>: <Code>$1.00 = 1,000,000</Code>. This avoids floating-point errors across millions of micro-transactions.
      </Callout>

      <SubHeading>3. Generate a virtual API key</SubHeading>
      <Prose>
        <p>Virtual keys are the credentials your AI application will use to authenticate with the Conduit gateway. They carry your identity and spending limits.</p>
      </Prose>
      <CodeBlock title="Create a virtual key" lang="bash">{`curl -X POST https://api.conduit.ai/wallet/v1/keys \\
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{ "name": "my-first-key" }'`}</CodeBlock>
      <CodeBlock title="Response — save the key, it's shown only once" lang="json">{`{
  "id": "a1b2c3d4-...",
  "name": "my-first-key",
  "key": "sk-conduit-aBcDeFgHiJkLmNoPqRsTuVwXyZ...",
  "key_prefix": "sk-conduit-aB",
  "rpm_limit": 60,
  "tpm_limit": 100000,
  "created_at": "2026-07-03T12:00:00Z"
}`}</CodeBlock>
      <Callout type="warning">
        Copy the full <Code>key</Code> value immediately — it is only returned at creation time and cannot be retrieved later.
      </Callout>

      <SubHeading>4. Make your first request</SubHeading>
      <Prose>
        <p>The Conduit gateway is OpenAI-compatible. Point any OpenAI SDK or <Code>curl</Code> at <Code>https://api.conduit.ai/v1</Code> and use your virtual key as the bearer token:</p>
      </Prose>
      <CodeBlock title="Chat completion via the gateway" lang="bash">{`curl -X POST https://api.conduit.ai/v1/chat/completions \\
  -H "Authorization: Bearer sk-conduit-aBcDeFgHiJkLmNoPqRsTuVwXyZ..." \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "gpt-4o",
    "messages": [
      { "role": "user", "content": "Hello, Conduit!" }
    ]
  }'`}</CodeBlock>
      <Prose>
        <p>The response includes standard OpenAI fields plus the <Code>X-Conduit-Cost-USD</Code> header showing the metered cost of the request. Usage is automatically deducted from your wallet balance.</p>
      </Prose>

      <SubHeading>5. Check your balance</SubHeading>
      <CodeBlock title="Get wallet balance" lang="bash">{`curl https://api.conduit.ai/wallet/v1/wallet \\
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"`}</CodeBlock>
      <CodeBlock title="Response" lang="json">{`{
  "wallet_id": "...",
  "balance_microdollars": 9985000,
  "held_microdollars": 0,
  "available_microdollars": 9985000,
  "currency": "USD"
}`}</CodeBlock>

      <Callout type="tip">
        <strong>Using the Node SDK?</strong> Install <Code>@conduit/sdk</Code> and skip straight to the <strong>Building an AI App</strong> guide for a full integration walkthrough.
      </Callout>
    </>
  );
}

function AuthenticationSection() {
  return (
    <>
      <SectionHeading>Authentication</SectionHeading>
      <Prose>
        <p>
          Conduit uses two authentication mechanisms depending on the context: <strong>JWT bearer tokens</strong> for wallet dashboard operations, and <strong>virtual API keys</strong> for gateway requests.
        </p>
      </Prose>

      <SubHeading>Wallet API — JWT tokens</SubHeading>
      <Prose>
        <p>
          All <Code>/wallet/v1/*</Code> endpoints require a JWT bearer token obtained via login or registration.
          Include it in the <Code>Authorization</Code> header:
        </p>
      </Prose>
      <CodeBlock lang="http">{`Authorization: Bearer eyJhbGciOiJIUzI1NiIs...`}</CodeBlock>

      <H3>Email / password login</H3>
      <CodeBlock title="POST /wallet/v1/auth/login" lang="bash">{`curl -X POST https://api.conduit.ai/wallet/v1/auth/login \\
  -H "Content-Type: application/json" \\
  -d '{
    "email": "you@example.com",
    "password": "your-password"
  }'`}</CodeBlock>

      <H3>Google OAuth</H3>
      <Prose>
        <p>
          Redirect the user to <Code>GET /wallet/v1/auth/oauth/google</Code> to start the Google OAuth flow.
          After consent, the frontend receives a <Code>code</Code> and <Code>state</Code> parameter and posts them back:
        </p>
      </Prose>
      <CodeBlock title="POST /wallet/v1/auth/oauth/google" lang="bash">{`curl -X POST https://api.conduit.ai/wallet/v1/auth/oauth/google \\
  -H "Content-Type: application/json" \\
  -d '{
    "code": "4/0AX4XfWh...",
    "state": "raw.signature"
  }'`}</CodeBlock>
      <Prose>
        <p>Both flows return the same <Code>AuthResponse</Code> shape with <Code>access_token</Code>, <Code>token_type</Code>, <Code>expires_in</Code>, and a <Code>user</Code> object.</p>
      </Prose>

      <SubHeading>Gateway API — Virtual keys</SubHeading>
      <Prose>
        <p>
          The gateway at <Code>/v1/*</Code> authenticates with <Code>sk-conduit-*</Code> virtual keys. These keys carry your identity, wallet binding, rate limits, and optional access group restrictions.
        </p>
      </Prose>
      <CodeBlock lang="http">{`Authorization: Bearer sk-conduit-aBcDeFgHiJkLmNoPqRsTuVwXyZ...`}</CodeBlock>

      <Callout type="info">
        Virtual keys are HMAC-hashed with a server pepper before storage. The plaintext is shown exactly once at creation time and cannot be recovered. If lost, revoke the key and create a new one.
      </Callout>

      <SubHeading>OAuth 2.1 — Delegated app tokens</SubHeading>
      <Prose>
        <p>
          Third-party AI applications can also authenticate via OAuth 2.1 delegated access tokens. When a user connects an app through the consent flow, the app receives a scoped JWT that can be used as a bearer token on both the wallet and gateway APIs. See the <strong>OAuth 2.1</strong> reference for the full flow.
        </p>
      </Prose>

      <SubHeading>Error responses</SubHeading>
      <div className="overflow-x-auto my-4">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-[var(--hairline)]">
              <th className="text-left py-2 pr-4 font-semibold">Status</th>
              <th className="text-left py-2 pr-4 font-semibold">Code</th>
              <th className="text-left py-2 font-semibold">Meaning</th>
            </tr>
          </thead>
          <tbody className="text-[var(--muted-foreground)]">
            <tr className="border-b border-[var(--hairline)]">
              <td className="py-2 pr-4"><Code>401</Code></td>
              <td className="py-2 pr-4"><Code>invalid_api_key</Code></td>
              <td className="py-2">Key is missing, malformed, or revoked.</td>
            </tr>
            <tr className="border-b border-[var(--hairline)]">
              <td className="py-2 pr-4"><Code>401</Code></td>
              <td className="py-2 pr-4"><Code>app_revoked</Code></td>
              <td className="py-2">The user has disconnected the app. Re-auth required.</td>
            </tr>
            <tr className="border-b border-[var(--hairline)]">
              <td className="py-2 pr-4"><Code>402</Code></td>
              <td className="py-2 pr-4"><Code>insufficient_balance</Code></td>
              <td className="py-2">Wallet balance too low for the requested operation.</td>
            </tr>
            <tr className="border-b border-[var(--hairline)]">
              <td className="py-2 pr-4"><Code>403</Code></td>
              <td className="py-2 pr-4"><Code>model_not_allowed</Code></td>
              <td className="py-2">The key's access group doesn't include this model.</td>
            </tr>
            <tr>
              <td className="py-2 pr-4"><Code>429</Code></td>
              <td className="py-2 pr-4"><Code>rate_limit_exceeded</Code></td>
              <td className="py-2">RPM or TPM limit exceeded. Back off and retry.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </>
  );
}

function ApiReferenceSection({ nav }: { nav: (s: Section) => void }) {
  return (
    <>
      <SectionHeading>API Reference</SectionHeading>
      <Prose>
        <p>
          Conduit exposes three API surfaces. All responses are JSON. All monetary values are integer microdollars (<Code>$1.00 = 1,000,000</Code>).
        </p>
      </Prose>

      <div className="grid gap-4 mt-8">
        <button onClick={() => nav("wallet-api")} className="card-soft card-soft-hover p-6 text-left">
          <div className="flex items-center gap-3 mb-2">
            <span className="w-8 h-8 rounded-lg bg-blue-100 text-blue-600 flex items-center justify-center text-sm font-bold">W</span>
            <h3 className="text-base font-semibold">Wallet API</h3>
          </div>
          <p className="text-sm text-[var(--muted-foreground)] mb-2">Account registration, login, balance, transactions, virtual keys, top-ups, connected apps, and access groups.</p>
          <code className="mono text-[13px] text-[var(--brand-primary)]">Base: /wallet/v1</code>
        </button>

        <button onClick={() => nav("gateway-api")} className="card-soft card-soft-hover p-6 text-left">
          <div className="flex items-center gap-3 mb-2">
            <span className="w-8 h-8 rounded-lg bg-emerald-100 text-emerald-600 flex items-center justify-center text-sm font-bold">G</span>
            <h3 className="text-base font-semibold">Gateway API</h3>
          </div>
          <p className="text-sm text-[var(--muted-foreground)] mb-2">OpenAI-compatible chat completions, model listing, and health check. Metered against your wallet balance.</p>
          <code className="mono text-[13px] text-[var(--brand-primary)]">Base: /v1</code>
        </button>

        <button onClick={() => nav("oauth")} className="card-soft card-soft-hover p-6 text-left">
          <div className="flex items-center gap-3 mb-2">
            <span className="w-8 h-8 rounded-lg bg-purple-100 text-purple-600 flex items-center justify-center text-sm font-bold">O</span>
            <h3 className="text-base font-semibold">OAuth 2.1</h3>
          </div>
          <p className="text-sm text-[var(--muted-foreground)] mb-2">Authorization code + PKCE, token exchange, refresh tokens, JWKS, and OpenID Connect discovery.</p>
          <code className="mono text-[13px] text-[var(--brand-primary)]">Base: /oauth</code>
        </button>
      </div>

      <SubHeading>Common conventions</SubHeading>
      <div className="space-y-3 mt-4">
        <div className="flex gap-3 text-sm">
          <span className="font-semibold text-[var(--ink)] shrink-0 w-32">Content-Type</span>
          <span className="text-[var(--muted-foreground)]"><Code>application/json</Code> for all request and response bodies (except OAuth token endpoint which accepts <Code>application/x-www-form-urlencoded</Code>).</span>
        </div>
        <div className="flex gap-3 text-sm">
          <span className="font-semibold text-[var(--ink)] shrink-0 w-32">Pagination</span>
          <span className="text-[var(--muted-foreground)]">Cursor-based. Pass <Code>cursor</Code> and <Code>limit</Code> (max 100) as query parameters. The response includes a <Code>next_cursor</Code> field.</span>
        </div>
        <div className="flex gap-3 text-sm">
          <span className="font-semibold text-[var(--ink)] shrink-0 w-32">Idempotency</span>
          <span className="text-[var(--muted-foreground)]">Mutating endpoints accept an <Code>Idempotency-Key</Code> header (UUID) for safe retries.</span>
        </div>
        <div className="flex gap-3 text-sm">
          <span className="font-semibold text-[var(--ink)] shrink-0 w-32">Money</span>
          <span className="text-[var(--muted-foreground)]">All monetary values are <strong>integer microdollars</strong>. <Code>$1.00 = 1,000,000</Code>.</span>
        </div>
      </div>
    </>
  );
}

function WalletApiSection() {
  return (
    <>
      <SectionHeading>Wallet API</SectionHeading>
      <Prose>
        <p>
          The Wallet API manages user accounts, balances, virtual keys, top-ups, and connected apps. All endpoints are under <Code>/wallet/v1</Code> and require JWT authentication unless marked as public.
        </p>
      </Prose>

      <SubHeading>Auth</SubHeading>
      <div className="card-soft p-4 my-4">
        <Endpoint method="POST" path="/wallet/v1/auth/register" description="Create a new account. Returns a JWT." />
        <Endpoint method="POST" path="/wallet/v1/auth/login" description="Login with email and password. Returns a JWT." />
        <Endpoint method="GET" path="/wallet/v1/auth/oauth/google" description="Redirect to Google OAuth consent screen." />
        <Endpoint method="POST" path="/wallet/v1/auth/oauth/google" description="Exchange Google code + state for a wallet session JWT." />
      </div>

      <H3>Register</H3>
      <ParamTable rows={[
        { name: "email", type: "string", req: true, desc: "Valid email address." },
        { name: "password", type: "string", req: true, desc: "Minimum 8 characters." },
      ]} />

      <H3>Login</H3>
      <ParamTable rows={[
        { name: "email", type: "string", req: true, desc: "Registered email." },
        { name: "password", type: "string", req: true, desc: "Account password." },
      ]} />

      <SubHeading>User</SubHeading>
      <div className="card-soft p-4 my-4">
        <Endpoint method="GET" path="/wallet/v1/me" description="Get the current user's profile (id, email, display_name)." />
      </div>

      <SubHeading>Wallet & Transactions</SubHeading>
      <div className="card-soft p-4 my-4">
        <Endpoint method="GET" path="/wallet/v1/wallet" description="Get wallet balance, held amount, and available funds." />
        <Endpoint method="GET" path="/wallet/v1/wallet/transactions" description="Paginated ledger history (deposits, usage, refunds, settlements)." />
        <Endpoint method="GET" path="/wallet/v1/usage" description="Paginated usage events with model, tokens, and cost." />
      </div>

      <H3>Wallet response</H3>
      <ParamTable rows={[
        { name: "wallet_id", type: "uuid", desc: "Unique wallet identifier." },
        { name: "balance_microdollars", type: "integer", desc: "Total balance including held funds." },
        { name: "held_microdollars", type: "integer", desc: "Funds currently reserved by active sessions." },
        { name: "available_microdollars", type: "integer", desc: "Balance minus holds — the amount available to spend." },
        { name: "currency", type: "string", desc: "Always \"USD\"." },
      ]} />

      <H3>Transaction pagination</H3>
      <ParamTable rows={[
        { name: "cursor", type: "string", desc: "Pagination cursor from a previous response." },
        { name: "limit", type: "integer", desc: "Items per page (default 20, max 100)." },
      ]} />

      <SubHeading>Top-ups</SubHeading>
      <div className="card-soft p-4 my-4">
        <Endpoint method="POST" path="/wallet/v1/topups/checkout" description="Create a Stripe Checkout session. Returns a checkout URL." />
      </div>
      <ParamTable rows={[
        { name: "amount_microdollars", type: "integer", req: true, desc: "Amount to add. Minimum 500,000 ($0.50)." },
      ]} />
      <Callout type="info">
        The checkout URL redirects the user to Stripe. On success, a webhook credits the wallet automatically. No polling is needed.
      </Callout>

      <SubHeading>Virtual Keys</SubHeading>
      <div className="card-soft p-4 my-4">
        <Endpoint method="GET" path="/wallet/v1/keys" description="List all virtual keys for the current user." />
        <Endpoint method="POST" path="/wallet/v1/keys" description="Create a new virtual key. The plaintext is returned once." />
        <Endpoint method="DELETE" path="/wallet/v1/keys/:keyId" description="Revoke a virtual key (soft-delete with revoked_at timestamp)." />
      </div>

      <H3>Create key parameters</H3>
      <ParamTable rows={[
        { name: "name", type: "string", desc: "Human-readable label for the key." },
        { name: "rpm_limit", type: "integer", desc: "Requests per minute limit (default: 60)." },
        { name: "tpm_limit", type: "integer", desc: "Tokens per minute limit (default: 100,000)." },
      ]} />

      <SubHeading>Connected Apps</SubHeading>
      <div className="card-soft p-4 my-4">
        <Endpoint method="GET" path="/wallet/v1/apps" description="List the user's connected apps with spend tracking." />
        <Endpoint method="POST" path="/wallet/v1/apps/:clientId/connect" description="Connect an app and set a per-app spending cap." />
        <Endpoint method="GET" path="/wallet/v1/apps/:installId" description="Get details for a specific connected app." />
        <Endpoint method="PATCH" path="/wallet/v1/apps/:installId" description="Update the per-app spending cap." />
        <Endpoint method="DELETE" path="/wallet/v1/apps/:installId" description="Revoke app access and all refresh tokens." />
      </div>

      <H3>Connect app parameters</H3>
      <ParamTable rows={[
        { name: "spend_limit_microdollars", type: "integer | null", desc: "Monthly or lifetime spending cap. Null = unlimited." },
        { name: "reset_period", type: "string", desc: "\"monthly\" (default) or \"lifetime\"." },
        { name: "display_name", type: "string", desc: "Optional display name override." },
      ]} />

      <SubHeading>Partner Apps (Admin)</SubHeading>
      <div className="card-soft p-4 my-4">
        <Endpoint method="POST" path="/wallet/v1/partner/:slug/apps" description="Register an OAuth client. Returns client_secret once." />
        <Endpoint method="GET" path="/wallet/v1/partner/:slug/apps" description="List all app registrations for a partner." />
      </div>
      <Prose>
        <p>
          Partner admin endpoints require the <Code>X-Partner-Admin-Token</Code> header. See the Partner onboarding guide for details.
        </p>
      </Prose>
    </>
  );
}

function GatewayApiSection() {
  return (
    <>
      <SectionHeading>Gateway API</SectionHeading>
      <Prose>
        <p>
          The Conduit gateway is a drop-in OpenAI-compatible proxy that meters every request against your wallet balance.
          Authenticate with an <Code>sk-conduit-*</Code> virtual key or an OAuth delegated access token.
          All endpoints are under <Code>/v1</Code>.
        </p>
      </Prose>

      <SubHeading>Endpoints</SubHeading>
      <div className="card-soft p-4 my-4">
        <Endpoint method="POST" path="/v1/chat/completions" description="Create a chat completion (OpenAI-compatible). Metered and billed." />
        <Endpoint method="GET" path="/v1/models" description="List available models." />
        <Endpoint method="GET" path="/v1/health" description="Health check (no auth required)." />
      </div>

      <SubHeading>Chat completions</SubHeading>
      <CodeBlock title="POST /v1/chat/completions" lang="bash">{`curl -X POST https://api.conduit.ai/v1/chat/completions \\
  -H "Authorization: Bearer sk-conduit-..." \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "gpt-4o",
    "messages": [
      { "role": "system", "content": "You are a helpful assistant." },
      { "role": "user", "content": "Explain quantum computing in one sentence." }
    ],
    "temperature": 0.7,
    "max_tokens": 256
  }'`}</CodeBlock>

      <H3>Request body</H3>
      <ParamTable rows={[
        { name: "model", type: "string", req: true, desc: "Model identifier (e.g. \"gpt-4o\", \"claude-3-opus\", \"gemini-pro\")." },
        { name: "messages", type: "array", req: true, desc: "Array of message objects with role (system/user/assistant/tool) and content." },
        { name: "stream", type: "boolean", desc: "Enable Server-Sent Events streaming (default: false)." },
        { name: "temperature", type: "number", desc: "Sampling temperature (0–2)." },
        { name: "max_tokens", type: "integer", desc: "Maximum tokens to generate." },
      ]} />

      <H3>Request headers</H3>
      <ParamTable rows={[
        { name: "Authorization", type: "string", req: true, desc: "Bearer token: sk-conduit-* key or OAuth access token." },
        { name: "X-Request-Id", type: "uuid", desc: "Idempotency key for billing. Auto-generated if omitted." },
      ]} />

      <H3>Response headers</H3>
      <ParamTable rows={[
        { name: "X-Request-Id", type: "string", desc: "The request ID used for billing correlation." },
        { name: "X-Conduit-Cost-USD", type: "string", desc: "The metered cost of this request in USD (e.g. \"0.003200\")." },
      ]} />

      <SubHeading>Response format</SubHeading>
      <CodeBlock title="200 OK" lang="json">{`{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1719993600,
  "model": "gpt-4o",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Quantum computing uses qubits..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 28,
    "completion_tokens": 15,
    "total_tokens": 43
  }
}`}</CodeBlock>

      <SubHeading>Error responses</SubHeading>
      <div className="overflow-x-auto my-4">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-[var(--hairline)]">
              <th className="text-left py-2 pr-4 font-semibold">Status</th>
              <th className="text-left py-2 pr-4 font-semibold">Error code</th>
              <th className="text-left py-2 font-semibold">Description</th>
            </tr>
          </thead>
          <tbody className="text-[var(--muted-foreground)]">
            <tr className="border-b border-[var(--hairline)]">
              <td className="py-2 pr-4"><Code>401</Code></td>
              <td className="py-2 pr-4"><Code>invalid_api_key</Code></td>
              <td className="py-2">The API key is missing, invalid, or has been revoked.</td>
            </tr>
            <tr className="border-b border-[var(--hairline)]">
              <td className="py-2 pr-4"><Code>402</Code></td>
              <td className="py-2 pr-4"><Code>insufficient_balance</Code></td>
              <td className="py-2">Wallet balance is too low. Top up to continue.</td>
            </tr>
            <tr className="border-b border-[var(--hairline)]">
              <td className="py-2 pr-4"><Code>403</Code></td>
              <td className="py-2 pr-4"><Code>model_not_allowed</Code></td>
              <td className="py-2">The key's access group does not include this model.</td>
            </tr>
            <tr>
              <td className="py-2 pr-4"><Code>429</Code></td>
              <td className="py-2 pr-4"><Code>rate_limit_exceeded</Code></td>
              <td className="py-2">RPM or TPM limit hit. Respect the Retry-After header.</td>
            </tr>
          </tbody>
        </table>
      </div>
      <Prose>
        <p>All error responses follow the shape:</p>
      </Prose>
      <CodeBlock title="Error response format" lang="json">{`{
  "error": {
    "code": "insufficient_balance",
    "message": "Wallet balance too low for this request.",
    "request_id": "abc-123-def"
  }
}`}</CodeBlock>

      <SubHeading>Models</SubHeading>
      <CodeBlock title="GET /v1/models" lang="bash">{`curl https://api.conduit.ai/v1/models \\
  -H "Authorization: Bearer sk-conduit-..."`}</CodeBlock>
      <Prose>
        <p>Returns the list of models available for your key's access group. If no access group is assigned, all active models are returned.</p>
      </Prose>

      <SubHeading>Using with OpenAI SDK</SubHeading>
      <Prose>
        <p>Since the gateway is OpenAI-compatible, you can use the official SDK by changing the base URL:</p>
      </Prose>
      <CodeBlock title="Python" lang="python">{`from openai import OpenAI

client = OpenAI(
    api_key="sk-conduit-...",
    base_url="https://api.conduit.ai/v1"
)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}]
)`}</CodeBlock>
      <CodeBlock title="Node.js" lang="typescript">{`import OpenAI from 'openai';

const client = new OpenAI({
  apiKey: 'sk-conduit-...',
  baseURL: 'https://api.conduit.ai/v1',
});

const response = await client.chat.completions.create({
  model: 'gpt-4o',
  messages: [{ role: 'user', content: 'Hello!' }],
});`}</CodeBlock>
    </>
  );
}

function OAuthSection() {
  return (
    <>
      <SectionHeading>OAuth 2.1</SectionHeading>
      <Prose>
        <p>
          Conduit implements OAuth 2.1 with PKCE for third-party AI applications to access user wallets with delegated permissions.
          This lets users connect apps like "Connect AI Wallet" without sharing credentials, and set per-app spending caps during the consent flow.
        </p>
      </Prose>

      <SubHeading>Endpoints</SubHeading>
      <div className="card-soft p-4 my-4">
        <Endpoint method="GET" path="/.well-known/openid-configuration" description="OIDC discovery metadata document." />
        <Endpoint method="GET" path="/oauth/authorize" description="Authorization endpoint — returns consent descriptor." />
        <Endpoint method="POST" path="/oauth/authorize/consent" description="Approve spend cap and receive an authorization code." />
        <Endpoint method="POST" path="/oauth/token" description="Exchange code for tokens, or refresh an access token." />
        <Endpoint method="GET" path="/oauth/userinfo" description="OIDC UserInfo — user profile + app install context." />
        <Endpoint method="GET" path="/oauth/jwks" description="JSON Web Key Set for token verification." />
      </div>
      <Callout type="info">
        OAuth endpoints are mounted at the API root (no <Code>/wallet/v1</Code> prefix).
      </Callout>

      <SubHeading>Authorization flow</SubHeading>
      <Prose>
        <p>Conduit uses the Authorization Code flow with PKCE (Proof Key for Code Exchange), which is the recommended grant type for all OAuth 2.1 clients.</p>
      </Prose>

      <H3>Step 1: Generate PKCE challenge</H3>
      <CodeBlock title="Generate code verifier and challenge" lang="javascript">{`// Generate a random code_verifier
const verifier = crypto.randomUUID() + crypto.randomUUID();

// Create the S256 challenge
const encoder = new TextEncoder();
const digest = await crypto.subtle.digest('SHA-256', encoder.encode(verifier));
const challenge = btoa(String.fromCharCode(...new Uint8Array(digest)))
  .replace(/\\+/g, '-').replace(/\\//g, '_').replace(/=+$/, '');`}</CodeBlock>

      <H3>Step 2: Redirect to authorize</H3>
      <Prose>
        <p>Redirect the user to Conduit's authorization endpoint. The user must have an active wallet session (JWT).</p>
      </Prose>
      <CodeBlock title="Authorization URL" lang="text">{`GET https://api.conduit.ai/oauth/authorize
  ?client_id=YOUR_CLIENT_ID
  &redirect_uri=https://yourapp.com/callback
  &response_type=code
  &scope=wallet:read wallet:charge
  &state=random-csrf-token
  &code_challenge=BASE64URL_CHALLENGE
  &code_challenge_method=S256`}</CodeBlock>

      <H3>Step 3: User consent</H3>
      <Prose>
        <p>
          Conduit displays a consent screen where the user reviews the requested permissions and sets a spending cap.
          On approval, Conduit calls <Code>POST /oauth/authorize/consent</Code> internally and redirects back to your <Code>redirect_uri</Code> with a <Code>code</Code> and <Code>state</Code>.
        </p>
      </Prose>
      <ParamTable rows={[
        { name: "client_id", type: "string", req: true, desc: "Your registered OAuth client ID." },
        { name: "redirect_uri", type: "string", req: true, desc: "Must match a registered redirect URI." },
        { name: "spend_limit_microdollars", type: "integer | null", desc: "Per-app spending cap (null = unlimited)." },
        { name: "reset_period", type: "string", desc: "\"monthly\" (default) or \"lifetime\"." },
        { name: "code_challenge", type: "string", desc: "S256 PKCE challenge." },
      ]} />

      <H3>Step 4: Exchange code for tokens</H3>
      <CodeBlock title="POST /oauth/token" lang="bash">{`curl -X POST https://api.conduit.ai/oauth/token \\
  -H "Content-Type: application/x-www-form-urlencoded" \\
  -d "grant_type=authorization_code" \\
  -d "code=AUTH_CODE_FROM_REDIRECT" \\
  -d "redirect_uri=https://yourapp.com/callback" \\
  -d "client_id=YOUR_CLIENT_ID" \\
  -d "client_secret=YOUR_CLIENT_SECRET" \\
  -d "code_verifier=YOUR_PKCE_VERIFIER"`}</CodeBlock>

      <H3>Token response</H3>
      <CodeBlock title="200 OK" lang="json">{`{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "id_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "dGhpcyBpcyBhIHJlZnJlc2g...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "wallet:read wallet:charge"
}`}</CodeBlock>

      <SubHeading>Refreshing tokens</SubHeading>
      <CodeBlock title="Refresh grant" lang="bash">{`curl -X POST https://api.conduit.ai/oauth/token \\
  -H "Content-Type: application/x-www-form-urlencoded" \\
  -d "grant_type=refresh_token" \\
  -d "refresh_token=dGhpcyBpcyBhIHJlZnJlc2g..." \\
  -d "client_id=YOUR_CLIENT_ID" \\
  -d "client_secret=YOUR_CLIENT_SECRET"`}</CodeBlock>

      <SubHeading>UserInfo</SubHeading>
      <Prose>
        <p>Retrieve the authenticated user's profile and app install context using the OAuth access token:</p>
      </Prose>
      <CodeBlock title="GET /oauth/userinfo" lang="bash">{`curl https://api.conduit.ai/oauth/userinfo \\
  -H "Authorization: Bearer OAUTH_ACCESS_TOKEN"`}</CodeBlock>

      <SubHeading>Error codes</SubHeading>
      <div className="overflow-x-auto my-4">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-[var(--hairline)]">
              <th className="text-left py-2 pr-4 font-semibold">Error</th>
              <th className="text-left py-2 font-semibold">Description</th>
            </tr>
          </thead>
          <tbody className="text-[var(--muted-foreground)]">
            <tr className="border-b border-[var(--hairline)]">
              <td className="py-2 pr-4"><Code>invalid_client</Code></td>
              <td className="py-2">Client ID or secret is wrong.</td>
            </tr>
            <tr className="border-b border-[var(--hairline)]">
              <td className="py-2 pr-4"><Code>invalid_grant</Code></td>
              <td className="py-2">Auth code is expired, already used, or PKCE verifier doesn't match.</td>
            </tr>
            <tr className="border-b border-[var(--hairline)]">
              <td className="py-2 pr-4"><Code>unsupported_grant_type</Code></td>
              <td className="py-2">Only authorization_code and refresh_token are supported.</td>
            </tr>
            <tr>
              <td className="py-2 pr-4"><Code>invalid_token</Code></td>
              <td className="py-2">Access token is expired or revoked (UserInfo endpoint).</td>
            </tr>
          </tbody>
        </table>
      </div>
    </>
  );
}

function GuideAiAppSection() {
  return (
    <>
      <SectionHeading>Building an AI App</SectionHeading>
      <Prose>
        <p>
          This guide walks you through integrating Conduit into a Node.js AI application using the <Code>@conduit/sdk</Code>.
          By the end, your app will pre-authorize wallet holds, call an LLM provider, and meter usage — all in under 30 lines.
        </p>
      </Prose>

      <SubHeading>Prerequisites</SubHeading>
      <Prose>
        <ul className="list-disc list-inside space-y-1">
          <li>A Conduit wallet with funds</li>
          <li>A virtual API key (<Code>sk-conduit-*</Code>)</li>
          <li>Node.js 18+ installed</li>
        </ul>
      </Prose>

      <SubHeading>1. Install the SDK</SubHeading>
      <CodeBlock title="Install" lang="bash">{`npm install @conduit/sdk openai`}</CodeBlock>

      <SubHeading>2. Initialize the client</SubHeading>
      <CodeBlock title="src/wallet.ts" lang="typescript">{`import { Conduit } from '@conduit/sdk';

export const wallet = new Conduit({
  apiKey: process.env.CONDUIT_API_KEY,   // sk-conduit-...
  baseUrl: process.env.CONDUIT_BASE_URL, // https://api.conduit.ai/v1
  flushIntervalMs: 5000,                 // batch flush every 5s
  maxBatchSize: 100,                     // or when buffer reaches 100 events
  retries: 3,                            // retry failed flushes with backoff
});`}</CodeBlock>

      <SubHeading>3. Authorize → Call LLM → Charge</SubHeading>
      <Prose>
        <p>The SDK follows a three-step pattern for every AI request:</p>
      </Prose>
      <CodeBlock title="src/chat.ts" lang="typescript">{`import { Conduit, PaymentRequiredError } from '@conduit/sdk';
import OpenAI from 'openai';

const wallet = new Conduit({ apiKey: process.env.CONDUIT_API_KEY });
const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

export async function chat(prompt: string) {
  // Step 1: Pre-authorize — checks balance and places a micro-hold
  const auth = await wallet.authorize({
    model: 'gpt-4o',
    maxTokens: 1024,
  });

  if (!auth.authorized) {
    throw new PaymentRequiredError('funds exhausted', {
      code: 'insufficient_balance',
    });
  }

  // Step 2: Call the LLM provider
  const res = await openai.chat.completions.create({
    model: 'gpt-4o',
    messages: [{ role: 'user', content: prompt }],
  });

  // Step 3: Report actual usage (fire-and-forget, batched)
  wallet.charge({
    requestId: auth.requestId,
    model: 'gpt-4o',
    inputTokens: res.usage!.prompt_tokens,
    outputTokens: res.usage!.completion_tokens,
    provider: 'openai',
  });

  return res.choices[0]!.message;
}`}</CodeBlock>

      <Callout type="tip">
        <Code>wallet.charge()</Code> is <strong>synchronous and non-blocking</strong>. Events are buffered in memory and flushed in batches to <Code>POST /v1/usage</Code>. Your application's main thread is never blocked.
      </Callout>

      <SubHeading>4. Handle 402 Payment Required</SubHeading>
      <Prose>
        <p>When the wallet balance or per-app allowance is exhausted, the SDK throws a <Code>PaymentRequiredError</Code>. Catch it and freeze compute before calling the LLM:</p>
      </Prose>
      <CodeBlock title="Error handling" lang="typescript">{`import { PaymentRequiredError, ForbiddenError } from '@conduit/sdk';

try {
  const result = await chat('Hello!');
} catch (err) {
  if (err instanceof PaymentRequiredError) {
    // err.code: 'insufficient_balance' | 'allowance_exceeded' | 'spend_limit_exceeded'
    return res.status(402).json({
      error: 'Please top up your Conduit wallet to continue.',
      code: err.code,
    });
  }
  if (err instanceof ForbiddenError) {
    // err.code: 'model_not_allowed'
    return res.status(403).json({
      error: 'This model is not available with your current access group.',
    });
  }
  throw err;
}`}</CodeBlock>

      <SubHeading>5. Serverless deployment</SubHeading>
      <Prose>
        <p>In serverless environments (Vercel, AWS Lambda, Cloudflare Workers), the background flush timer may not fire before the process freezes. Disable the timer and manually flush:</p>
      </Prose>
      <CodeBlock title="Serverless handler" lang="typescript">{`export async function handler(req: Request) {
  const wallet = new Conduit({
    apiKey: process.env.CONDUIT_API_KEY,
    flushIntervalMs: 0,  // no background timer
  });

  try {
    const auth = await wallet.authorize({ model: 'gpt-4o' });
    // ... call provider, wallet.charge(...) ...
    return new Response('OK', { status: 200 });
  } finally {
    await wallet.flush();  // always flush before exit
  }
}`}</CodeBlock>

      <SubHeading>6. Graceful shutdown</SubHeading>
      <Prose>
        <p>For long-running servers, call <Code>wallet.shutdown()</Code> on process exit to stop the timer and flush any remaining events:</p>
      </Prose>
      <CodeBlock title="Graceful shutdown" lang="typescript">{`process.on('SIGTERM', async () => {
  await wallet.shutdown();
  process.exit(0);
});`}</CodeBlock>

      <SubHeading>Using the gateway directly</SubHeading>
      <Prose>
        <p>
          If you don't need the SDK's batching and pre-authorization, you can use the Conduit gateway as a drop-in OpenAI proxy.
          The gateway handles metering automatically — just point your OpenAI client at <Code>https://api.conduit.ai/v1</Code> with your <Code>sk-conduit-*</Code> key.
          See the <strong>Gateway API</strong> reference for details.
        </p>
      </Prose>
    </>
  );
}

function GuideSpendingCapsSection() {
  return (
    <>
      <SectionHeading>Managing Spending Caps</SectionHeading>
      <Prose>
        <p>
          Spending caps are Conduit's safety switch. They let you set per-app limits so a buggy or looping AI agent can only drain its isolated allowance — never your full wallet balance.
        </p>
      </Prose>

      <SubHeading>How spending caps work</SubHeading>
      <Prose>
        <p>
          When you connect an AI application to your wallet (via OAuth consent or the dashboard), you choose a <strong>spending cap</strong> and a <strong>reset period</strong>:
        </p>
      </Prose>
      <div className="overflow-x-auto my-4">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-[var(--hairline)]">
              <th className="text-left py-2 pr-4 font-semibold">Reset period</th>
              <th className="text-left py-2 font-semibold">Behavior</th>
            </tr>
          </thead>
          <tbody className="text-[var(--muted-foreground)]">
            <tr className="border-b border-[var(--hairline)]">
              <td className="py-2 pr-4 font-medium text-[var(--ink)]">Monthly</td>
              <td className="py-2">The <Code>allowance_spent</Code> counter resets to zero at the start of each calendar month. Good for ongoing usage.</td>
            </tr>
            <tr>
              <td className="py-2 pr-4 font-medium text-[var(--ink)]">Lifetime</td>
              <td className="py-2">The cap is a one-time total. Once spent, the app is blocked until you raise the limit. Good for trial or capped experiments.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <Callout type="info">
        Setting a spending cap to <Code>null</Code> means <strong>unlimited</strong> — the app can spend up to your full wallet balance. Use with caution.
      </Callout>

      <SubHeading>Setting a cap via the Dashboard</SubHeading>
      <Prose>
        <p>
          Navigate to <strong>Dashboard → Connected Apps</strong>. Click on an app to adjust its spending cap, or connect a new app with a preset limit.
        </p>
      </Prose>

      <SubHeading>Setting a cap via the API</SubHeading>
      <H3>When connecting an app</H3>
      <CodeBlock title="Connect with a $5/month cap" lang="bash">{`curl -X POST https://api.conduit.ai/wallet/v1/apps/CLIENT_ID/connect \\
  -H "Authorization: Bearer YOUR_JWT" \\
  -H "Content-Type: application/json" \\
  -d '{
    "spend_limit_microdollars": 5000000,
    "reset_period": "monthly"
  }'`}</CodeBlock>

      <H3>Updating an existing cap</H3>
      <CodeBlock title="Raise the cap to $20/month" lang="bash">{`curl -X PATCH https://api.conduit.ai/wallet/v1/apps/INSTALL_ID \\
  -H "Authorization: Bearer YOUR_JWT" \\
  -H "Content-Type: application/json" \\
  -d '{ "spend_limit_microdollars": 20000000 }'`}</CodeBlock>

      <H3>During OAuth consent</H3>
      <Prose>
        <p>
          When a user connects your app via OAuth, the consent screen includes a spending cap selector.
          The chosen cap is passed in the <Code>POST /oauth/authorize/consent</Code> body as <Code>spend_limit_microdollars</Code>.
        </p>
      </Prose>

      <SubHeading>What happens when the cap is hit?</SubHeading>
      <Prose>
        <p>When an app's <Code>allowance_spent</Code> reaches <Code>spend_limit</Code>:</p>
        <ol className="list-decimal list-inside space-y-2">
          <li>The gateway returns <Code>402 Payment Required</Code> with code <Code>allowance_exceeded</Code>.</li>
          <li>The SDK throws a <Code>PaymentRequiredError</Code> so your app can freeze compute cleanly.</li>
          <li>All further requests from that app's tokens are blocked.</li>
          <li>Other apps connected to the same wallet are <strong>unaffected</strong> — isolation is per-app.</li>
        </ol>
      </Prose>

      <Callout type="tip">
        <strong>Best practice:</strong> Start with a low cap ($2–$5/month) when testing a new integration, then raise it once you're confident the app handles billing correctly.
      </Callout>

      <SubHeading>Monitoring spend</SubHeading>
      <Prose>
        <p>Check an app's current spending against its cap:</p>
      </Prose>
      <CodeBlock title="Get connected app details" lang="bash">{`curl https://api.conduit.ai/wallet/v1/apps/INSTALL_ID \\
  -H "Authorization: Bearer YOUR_JWT"`}</CodeBlock>
      <CodeBlock title="Response" lang="json">{`{
  "install_id": "...",
  "client_id": "cursor-ai",
  "app_name": "Cursor",
  "spend_limit_microdollars": 5000000,
  "allowance_spent_microdollars": 1250000,
  "allowance_reset_period": "monthly",
  "consented_at": "2026-06-15T10:30:00Z"
}`}</CodeBlock>
      <Prose>
        <p>
          In this example, Cursor has used $1.25 of a $5.00 monthly cap — 75% of the budget remains.
        </p>
      </Prose>
    </>
  );
}

function GuideAccessGroupsSection() {
  return (
    <>
      <SectionHeading>Access Groups</SectionHeading>
      <Prose>
        <p>
          Access groups let you control which AI models a virtual key can use.
          Assign an access group to a key to restrict it to a curated set of models — useful for cost control, compliance, or team management.
        </p>
      </Prose>

      <SubHeading>How access groups work</SubHeading>
      <Prose>
        <p>
          An access group is a named collection of model slugs (e.g. <Code>gpt-4o</Code>, <Code>claude-3-opus</Code>).
          When a virtual key has an access group assigned, gateway requests with that key can only use models in the group.
          Requests for other models return <Code>403 Forbidden</Code> with code <Code>model_not_allowed</Code>.
        </p>
      </Prose>

      <Callout type="info">
        Keys without an access group can use <strong>all active models</strong>. Assign a group to restrict access.
      </Callout>

      <SubHeading>Managing access groups in the Dashboard</SubHeading>
      <Prose>
        <p>
          Navigate to <strong>Dashboard → Access Groups</strong> to create, edit, and delete access groups.
          You can browse the full model catalog and toggle models on or off for each group.
        </p>
      </Prose>

      <SubHeading>Managing via the API</SubHeading>

      <H3>Create an access group</H3>
      <CodeBlock title='Create a "Budget models" group' lang="bash">{`curl -X POST https://api.conduit.ai/wallet/v1/access-groups \\
  -H "Authorization: Bearer YOUR_JWT" \\
  -H "Content-Type: application/json" \\
  -d '{
    "name": "Budget models",
    "description": "Cost-effective models for development",
    "model_slugs": ["gpt-4o-mini", "claude-3-haiku", "gemini-flash"]
  }'`}</CodeBlock>

      <H3>List access groups</H3>
      <CodeBlock title="List all groups" lang="bash">{`curl https://api.conduit.ai/wallet/v1/access-groups \\
  -H "Authorization: Bearer YOUR_JWT"`}</CodeBlock>
      <CodeBlock title="Response" lang="json">{`{
  "data": [
    {
      "id": "550e8400-...",
      "name": "Budget models",
      "description": "Cost-effective models for development",
      "model_slugs": ["gpt-4o-mini", "claude-3-haiku", "gemini-flash"]
    },
    {
      "id": "660f9500-...",
      "name": "Premium",
      "description": "All frontier models",
      "model_slugs": ["gpt-4o", "claude-3-opus", "gemini-pro"]
    }
  ]
}`}</CodeBlock>

      <H3>Update an access group</H3>
      <CodeBlock title="Add a model to the group" lang="bash">{`curl -X PATCH https://api.conduit.ai/wallet/v1/access-groups/GROUP_ID \\
  -H "Authorization: Bearer YOUR_JWT" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model_slugs": ["gpt-4o-mini", "claude-3-haiku", "gemini-flash", "gemini-pro"]
  }'`}</CodeBlock>

      <H3>Delete an access group</H3>
      <CodeBlock title="Delete a group" lang="bash">{`curl -X DELETE https://api.conduit.ai/wallet/v1/access-groups/GROUP_ID \\
  -H "Authorization: Bearer YOUR_JWT"`}</CodeBlock>
      <Callout type="warning">
        Deleting an access group removes the restriction from all keys that were using it. Those keys will then have access to <strong>all models</strong>.
      </Callout>

      <SubHeading>Assigning an access group to a key</SubHeading>
      <Prose>
        <p>You can assign an access group when creating a key, or update it later:</p>
      </Prose>

      <H3>At key creation</H3>
      <CodeBlock title="Create a key with an access group" lang="bash">{`curl -X POST https://api.conduit.ai/wallet/v1/keys \\
  -H "Authorization: Bearer YOUR_JWT" \\
  -H "Content-Type: application/json" \\
  -d '{
    "name": "dev-key",
    "access_group_id": "550e8400-...",
    "rpm_limit": 30,
    "tpm_limit": 50000
  }'`}</CodeBlock>

      <H3>Update an existing key</H3>
      <CodeBlock title="Assign a different access group" lang="bash">{`curl -X PATCH https://api.conduit.ai/wallet/v1/keys/KEY_ID/access-group \\
  -H "Authorization: Bearer YOUR_JWT" \\
  -H "Content-Type: application/json" \\
  -d '{ "access_group_id": "660f9500-..." }'`}</CodeBlock>
      <Prose>
        <p>Set <Code>access_group_id</Code> to <Code>null</Code> to remove the restriction and grant access to all models.</p>
      </Prose>

      <SubHeading>Browsing the model catalog</SubHeading>
      <Prose>
        <p>List all models available on Conduit to see what slugs you can add to groups:</p>
      </Prose>
      <CodeBlock title="List available models" lang="bash">{`curl https://api.conduit.ai/wallet/v1/models \\
  -H "Authorization: Bearer YOUR_JWT"`}</CodeBlock>

      <SubHeading>Common patterns</SubHeading>
      <div className="space-y-4 mt-4">
        <div className="card-soft p-5">
          <h4 className="font-semibold text-sm mb-1">🏗️ Dev vs. Production keys</h4>
          <p className="text-sm text-[var(--muted-foreground)] m-0">Create a "Budget" group with cheap models for development, and a "Production" group with frontier models for live traffic.</p>
        </div>
        <div className="card-soft p-5">
          <h4 className="font-semibold text-sm mb-1">👥 Team model governance</h4>
          <p className="text-sm text-[var(--muted-foreground)] m-0">Restrict interns or cost-sensitive teams to efficient models while power users get access to GPT-4o and Claude Opus.</p>
        </div>
        <div className="card-soft p-5">
          <h4 className="font-semibold text-sm mb-1">🔒 Compliance controls</h4>
          <p className="text-sm text-[var(--muted-foreground)] m-0">Limit keys to approved providers only — e.g. only Google models for a team that requires data residency guarantees.</p>
        </div>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ */
/*  Main page                                                          */
/* ------------------------------------------------------------------ */

function DocsPage() {
  const [active, setActive] = useState<Section>("introduction");

  const navigate = useCallback((s: Section) => {
    setActive(s);
    if (typeof window !== "undefined") {
      window.history.replaceState(null, "", `#${s}`);
      window.scrollTo({ top: 0, behavior: "instant" });
    }
  }, []);

  // Sync hash after mount and on back/forward without changing the SSR render.
  useEffect(() => {
    const onHash = () => {
      const h = window.location.hash.replace("#", "") as Section;
      if (SECTIONS.some((s) => s.key === h)) setActive(h);
    };
    onHash();
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const groups = [...new Set(SECTIONS.map((s) => s.group))];

  const content: Record<Section, ReactNode> = {
    introduction: <IntroductionSection nav={navigate} />,
    quickstart: <QuickstartSection />,
    authentication: <AuthenticationSection />,
    "api-reference": <ApiReferenceSection nav={navigate} />,
    "wallet-api": <WalletApiSection />,
    "gateway-api": <GatewayApiSection />,
    oauth: <OAuthSection />,
    "guide-ai-app": <GuideAiAppSection />,
    "guide-spending-caps": <GuideSpendingCapsSection />,
    "guide-access-groups": <GuideAccessGroupsSection />,
  };

  return (
    <div className="bg-[var(--surface)] text-[var(--ink)] min-h-screen flex flex-col">
      <MarketingNav />
      <div className="flex-1 mx-auto max-w-6xl w-full px-6 py-12 flex flex-col md:flex-row gap-12">
        {/* Sidebar */}
        <aside className="w-full md:w-64 shrink-0">
          <div className="sticky top-24 space-y-8">
            {groups.map((group) => (
              <div key={group}>
                <h4 className="font-semibold mb-3 tracking-tight">{group}</h4>
                <ul className="space-y-2.5 text-sm text-[var(--muted-foreground)]">
                  {SECTIONS.filter((s) => s.group === group).map((s) => (
                    <li key={s.key}>
                      <button
                        onClick={() => navigate(s.key)}
                        className={`text-left w-full transition-colors ${
                          active === s.key
                            ? "text-[var(--brand-primary)] font-medium"
                            : "hover:text-[var(--ink)]"
                        }`}
                      >
                        {s.label}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </aside>

        {/* Main content */}
        <main className="flex-1 min-w-0 max-w-3xl">
          {content[active]}
        </main>
      </div>
      <MarketingFooter />
    </div>
  );
}
