import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import { z } from "zod";
import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { zodValidator, fallback } from "@tanstack/zod-adapter";
import { ApiError, api } from "@/lib/api";
import { setJwt } from "@/lib/auth";
import { Button } from "@/components/ui-prim/button";
import { Field } from "@/components/ui-prim/field";
import { RingMark } from "@/components/ring-mark";
import { Halo } from "@/components/halo";

const search = z.object({
  tab: fallback(z.enum(["login", "register"]), "login").default("login"),
  redirect: fallback(z.string(), "/dashboard").default("/dashboard"),
});

export const Route = createFileRoute("/auth")({
  validateSearch: zodValidator(search),
  head: () => ({
    meta: [
      { title: "Sign in — Conduit" },
      { name: "description", content: "Sign in or create a Conduit account." },
    ],
  }),
  component: AuthPage,
});

interface AuthResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: { id: string; email: string; display_name?: string };
}

function AuthPage() {
  const { tab, redirect } = Route.useSearch();
  const navigate = useNavigate();
  const oauthRan = useRef(false);
  const [oauthStatus, setOauthStatus] = useState<string | null>(null);

  useEffect(() => {
    if (oauthRan.current || typeof window === "undefined") return;

    const sp = new URLSearchParams(window.location.search);
    const code = sp.get("code");
    const state = sp.get("state");
    const error = sp.get("error");
    const errorDescription = sp.get("error_description");

    if (!code && !error) return;
    oauthRan.current = true;

    if (error) {
      setOauthStatus(`Google sign-in failed: ${errorDescription || error}`);
      setTimeout(
        () => navigate({ to: "/auth", search: { tab: "login", redirect: "/dashboard" } }),
        2500,
      );
      return;
    }

    if (!state) {
      setOauthStatus("Google sign-in failed: missing OAuth state.");
      setTimeout(
        () => navigate({ to: "/auth", search: { tab: "login", redirect: "/dashboard" } }),
        2500,
      );
      return;
    }

    setOauthStatus("Finishing sign-in...");
    (async () => {
      try {
        const res = await api<AuthResponse>("/wallet/v1/auth/oauth/google/callback", {
          method: "POST",
          body: { code, state },
        });
        setJwt(res.access_token);
        navigate({ to: (sp.get("redirect") || "/dashboard") as "/dashboard" });
      } catch (err) {
        const message = err instanceof Error ? err.message : "Google sign-in failed.";
        setOauthStatus(`Google sign-in failed: ${message}`);
        setTimeout(
          () => navigate({ to: "/auth", search: { tab: "login", redirect: "/dashboard" } }),
          3000,
        );
      }
    })();
  }, [navigate]);

  if (oauthStatus) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--surface)] px-6 text-center text-sm text-[var(--muted-foreground)]">
        {oauthStatus}
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col bg-[var(--surface)] text-[var(--ink)] relative overflow-hidden">
      <Halo />
      <header className="px-6 py-6">
        <Link to="/" className="inline-flex items-center">
          <RingMark withWordmark size={26} />
        </Link>
      </header>
      <main className="flex-1 flex items-center justify-center px-6 pb-16">
        <div className="w-full max-w-md card-soft p-8">
          <div className="flex items-center gap-1 mb-6 rounded-full bg-[var(--surface-alt)] p-1">
            <TabBtn active={tab === "login"} onClick={() => navigate({ to: "/auth", search: { tab: "login", redirect } })}>
              Sign in
            </TabBtn>
            <TabBtn active={tab === "register"} onClick={() => navigate({ to: "/auth", search: { tab: "register", redirect } })}>
              Create account
            </TabBtn>
          </div>
          {tab === "login" ? <LoginForm redirect={redirect} /> : <RegisterForm redirect={redirect} />}
          <div className="mt-6">
            <button
              onClick={() => {
                window.location.href = `${(import.meta.env.VITE_API_BASE_URL as string | undefined) ?? ""}/wallet/v1/auth/oauth/google`;
              }}
              className="w-full h-11 rounded-full border border-[var(--hairline)] bg-white hover:border-[var(--brand-secondary)] flex items-center justify-center gap-2 text-sm font-medium"
            >
              <GoogleIcon /> Continue with Google
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}

function TabBtn({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 h-9 rounded-full text-sm font-medium transition-all ${
        active ? "bg-white text-[var(--ink)] shadow-sm" : "text-[var(--muted-foreground)] hover:text-[var(--ink)]"
      }`}
    >
      {children}
    </button>
  );
}

function LoginForm({ redirect }: { redirect: string }) {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      return api<AuthResponse>("/wallet/v1/auth/login", {
        method: "POST",
        body: { email, password },
      });
    },
    onSuccess: (data) => {
      setJwt(data.access_token);
      navigate({ to: redirect as "/dashboard" });
    },
    onError: (e: ApiError) => {
      setErr(e.code === "invalid_credentials" ? "Email or password is incorrect." : e.message);
    },
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setErr(null);
        mutation.mutate();
      }}
      className="space-y-4"
    >
      <h1 className="text-2xl font-semibold tracking-tight">Welcome back</h1>
      <Field label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
      <Field label="Password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} />
      {err && <p className="text-sm text-[var(--destructive)]">{err}</p>}
      <Button type="submit" className="w-full" loading={mutation.isPending}>
        Sign in
      </Button>
    </form>
  );
}

function RegisterForm({ redirect }: { redirect: string }) {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () =>
      api<AuthResponse>("/wallet/v1/auth/register", {
        method: "POST",
        body: { email, password, display_name: displayName || undefined },
      }),
    onSuccess: (data) => {
      setJwt(data.access_token);
      navigate({ to: redirect as "/dashboard" });
    },
    onError: (e: ApiError) => {
      setErr(e.code === "email_taken" ? "An account with that email already exists." : e.message);
    },
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setErr(null);
        if (password.length < 8) {
          setErr("Password must be at least 8 characters.");
          return;
        }
        mutation.mutate();
      }}
      className="space-y-4"
    >
      <h1 className="text-2xl font-semibold tracking-tight">Create your wallet</h1>
      <Field label="Display name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="Optional" />
      <Field label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      <Field
        label="Password"
        type="password"
        required
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        hint="At least 8 characters."
      />
      {err && <p className="text-sm text-[var(--destructive)]">{err}</p>}
      <Button type="submit" className="w-full" loading={mutation.isPending}>
        Create account
      </Button>
      <p className="text-xs text-[var(--muted-foreground)] text-center">
        By creating an account, you agree to Conduit's Terms and Privacy Policy.
      </p>
    </form>
  );
}

function GoogleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3c-1.6 4.6-6 8-11.3 8-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34.5 6.1 29.5 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.3-.4-3.5z"/>
      <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 16.1 19 13 24 13c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34.5 6.1 29.5 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"/>
      <path fill="#4CAF50" d="M24 44c5.3 0 10.1-2 13.8-5.3l-6.4-5.4C29.3 34.7 26.8 36 24 36c-5.3 0-9.7-3.4-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z"/>
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.3-2.3 4.2-4.1 5.5l6.4 5.4C40.7 36 44 30.5 44 24c0-1.3-.1-2.3-.4-3.5z"/>
    </svg>
  );
}
