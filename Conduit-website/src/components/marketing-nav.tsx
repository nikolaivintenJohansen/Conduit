import { Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { RingMark } from "./ring-mark";
import { Button } from "./ui-prim/button";
import { useAuth } from "@/lib/auth";

const NAV = [
  { to: "/developers", label: "Developers" },
  { to: "/pricing", label: "Pricing" },
  { to: "/security", label: "Security" },
  { to: "/docs", label: "Docs" },
] as const;

export function MarketingNav() {
  const [scrolled, setScrolled] = useState(false);
  const { isAuthenticated } = useAuth();

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`sticky top-0 z-50 w-full transition-all ${
        scrolled ? "nav-blur" : "bg-transparent"
      }`}
    >
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
        <Link to="/" className="flex items-center" aria-label="Conduit home">
          <RingMark withWordmark size={30} />
        </Link>

        <nav className="hidden md:flex items-center gap-1">
          {NAV.map((n) => (
            <Link
              key={n.to}
              to={n.to}
              className="rounded-full px-3 py-1.5 text-sm font-medium text-[var(--ink)] hover:bg-[var(--surface-alt)] transition-colors"
              activeProps={{ className: "text-[var(--brand-primary)]" }}
            >
              {n.label}
            </Link>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          {isAuthenticated ? (
            <Link to="/dashboard">
              <Button size="sm" variant="primary">
                Dashboard
              </Button>
            </Link>
          ) : (
            <>
              <Link to="/auth" search={{ tab: "login" }} className="hidden sm:block">
                <Button size="sm" variant="ghost">
                  Sign in
                </Button>
              </Link>
              <Link to="/auth" search={{ tab: "register" }}>
                <Button size="sm" variant="primary">
                  Sign up free
                </Button>
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}

export function MarketingFooter() {
  return (
    <footer className="border-t border-[var(--hairline)] bg-[var(--surface-alt)] mt-32">
      <div className="mx-auto max-w-7xl px-6 py-12 grid grid-cols-2 md:grid-cols-4 gap-8 text-sm">
        <div className="col-span-2 md:col-span-1">
          <RingMark withWordmark size={26} />
          <p className="mt-3 text-[var(--muted-foreground)] max-w-xs">
            One prepaid wallet for every AI app you use.
          </p>
        </div>
        <FooterCol
          title="Product"
          links={[
            { to: "/pricing", label: "Pricing" },
            { to: "/security", label: "Security" },
            { to: "/developers", label: "For developers" },
          ]}
        />
        <FooterCol
          title="Resources"
          links={[
            { to: "/docs", label: "Documentation" },
            { to: "/developers", label: "API reference" },
          ]}
        />
        <FooterCol
          title="Company"
          links={[
            { to: "/", label: "About" },
            { to: "/", label: "Contact" },
          ]}
        />
      </div>
      <div className="border-t border-[var(--hairline)]">
        <div className="mx-auto max-w-7xl px-6 py-6 flex items-center justify-between text-xs text-[var(--muted-foreground)]">
          <span>© {new Date().getFullYear()} Conduit. All rights reserved.</span>
          <span>USD only · Prepaid micro-charging</span>
        </div>
      </div>
    </footer>
  );
}

function FooterCol({ title, links }: { title: string; links: { to: string; label: string }[] }) {
  return (
    <div>
      <h4 className="text-[11px] uppercase tracking-wider text-[var(--muted-foreground)] mb-3">{title}</h4>
      <ul className="space-y-2">
        {links.map((l, i) => (
          <li key={i}>
            <Link to={l.to} className="text-[var(--ink)] hover:text-[var(--brand-primary)] transition-colors">
              {l.label}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
