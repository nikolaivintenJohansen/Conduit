import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useRef } from "react";
import { api } from "@/lib/api";
import { setJwt } from "@/lib/auth";

export const Route = createFileRoute("/auth/google/callback")({
  component: GoogleCallback,
});

function GoogleCallback() {
  const navigate = useNavigate();
  const ran = useRef(false);
  useEffect(() => {
    if (ran.current) return;
    ran.current = true;
    const sp = new URLSearchParams(window.location.search);
    const code = sp.get("code");
    const state = sp.get("state");
    if (!code) {
      navigate({ to: "/auth", search: { tab: "login", redirect: "/dashboard" } });
      return;
    }
    (async () => {
      try {
        const res = await api<{ access_token: string }>("/wallet/v1/auth/oauth/google/callback", {
          method: "POST",
          body: { code, state },
        });
        setJwt(res.access_token);
        navigate({ to: "/dashboard" });
      } catch {
        navigate({ to: "/auth", search: { tab: "login", redirect: "/dashboard" } });
      }
    })();
  }, [navigate]);
  return (
    <div className="min-h-screen flex items-center justify-center text-sm text-[var(--muted-foreground)]">
      Finishing sign-in…
    </div>
  );
}
