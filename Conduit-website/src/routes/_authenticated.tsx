import { createFileRoute, Link, Outlet, redirect, useNavigate, useRouterState } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  LayoutDashboard,
  Activity,
  ArrowLeftRight,
  KeyRound,
  Layers,
  AppWindow,
  Settings,
  LogOut,
} from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { clearJwt, getJwt, useAuth } from "@/lib/auth";
import { RingMark } from "@/components/ring-mark";

export interface MeResponse {
  id: string;
  email: string;
  display_name?: string;
  wallet_id: string;
  balance_microdollars: number;
  held_microdollars: number;
  available_microdollars: number;
  currency: string;
  low_balance_threshold_microdollars: number | null;
  spend_limit_microdollars: number | null;
  monthly_spend_microdollars: number;
}

export const Route = createFileRoute("/_authenticated")({
  beforeLoad: ({ location }) => {
    if (typeof window === "undefined") return;
    if (!getJwt()) {
      throw redirect({
        to: "/auth",
        search: { tab: "login", redirect: location.pathname + location.search },
      });
    }
  },
  component: DashLayout,
});

const NAV: { to: string; label: string; icon: typeof LayoutDashboard; exact?: boolean }[] = [
  { to: "/dashboard", label: "Overview", icon: LayoutDashboard, exact: true },
  { to: "/dashboard/usage", label: "Usage", icon: Activity },
  { to: "/dashboard/transactions", label: "Transactions", icon: ArrowLeftRight },
  { to: "/dashboard/keys", label: "API Keys", icon: KeyRound },
  { to: "/dashboard/access-groups", label: "Access Groups", icon: Layers },
  { to: "/dashboard/apps", label: "Connected Apps", icon: AppWindow },
  { to: "/dashboard/settings", label: "Settings", icon: Settings },
];

function DashLayout() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { isAuthenticated } = useAuth();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    if (!isAuthenticated && typeof window !== "undefined") {
      navigate({ to: "/auth", search: { tab: "login", redirect: "/dashboard" } });
    }
  }, [isAuthenticated, navigate]);

  const meQ = useQuery({
    queryKey: ["me"],
    queryFn: () => api<MeResponse>("/wallet/v1/me"),
    enabled: isAuthenticated,
    retry: false,
    staleTime: 30_000,
  });

  async function signOut() {
    try {
      await qc.cancelQueries();
      await api("/wallet/v1/auth/logout", { method: "POST" });
    } catch {
      /* ignore */
    } finally {
      qc.clear();
      clearJwt();
      navigate({ to: "/auth", search: { tab: "login", redirect: "/dashboard" }, replace: true });
    }
  }

  return (
    <div className="min-h-screen bg-[var(--surface-alt)] text-[var(--ink)]">
      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 w-60 bg-white border-r border-[var(--hairline)] flex flex-col transition-transform md:translate-x-0 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="px-5 h-16 flex items-center border-b border-[var(--hairline)]">
          <Link to="/" className="flex items-center" onClick={() => setMobileOpen(false)}>
            <RingMark withWordmark size={26} />
          </Link>
        </div>
        <nav className="flex-1 p-3 space-y-0.5">
          {NAV.map((n) => {
            const active = n.exact ? pathname === n.to : pathname.startsWith(n.to);
            const Icon = n.icon;
            return (
              <Link
                key={n.to}
                to={n.to as "/dashboard"}
                onClick={() => setMobileOpen(false)}
                className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  active
                    ? "bg-[#eaf2ff] text-[var(--brand-primary)]"
                    : "text-[var(--ink)] hover:bg-[var(--surface-alt)]"
                }`}
              >
                <Icon className="h-4 w-4" />
                {n.label}
              </Link>
            );
          })}
        </nav>
        <div className="p-3 border-t border-[var(--hairline)]">
          <div className="px-3 py-2">
            <div className="text-xs text-[var(--muted-foreground)]">Signed in as</div>
            <div className="text-sm font-medium truncate">{meQ.data?.email ?? "…"}</div>
          </div>
          <button
            onClick={signOut}
            className="w-full flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium text-[var(--ink)] hover:bg-[var(--surface-alt)]"
          >
            <LogOut className="h-4 w-4" /> Sign out
          </button>
        </div>
      </aside>

      {/* Top bar */}
      <div className="md:pl-60">
        <header className="h-16 bg-white border-b border-[var(--hairline)] flex items-center justify-between px-6 sticky top-0 z-30">
          <button
            className="md:hidden text-sm font-medium"
            onClick={() => setMobileOpen((o) => !o)}
            aria-label="Toggle menu"
          >
            ☰
          </button>
          <div className="text-sm text-[var(--muted-foreground)] hidden md:block">
            {greeting()} {meQ.data?.display_name || meQ.data?.email?.split("@")[0] || ""}
          </div>
          <div className="text-xs text-[var(--muted-foreground)] mono">
            wallet {meQ.data?.wallet_id?.slice(0, 8) ?? "…"}
          </div>
        </header>
        <main className="p-6 md:p-8 max-w-6xl mx-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning,";
  if (h < 18) return "Good afternoon,";
  return "Good evening,";
}
