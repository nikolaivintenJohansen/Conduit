import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Outlet,
  Link,
  createRootRouteWithContext,
  useRouter,
  HeadContent,
  Scripts,
} from "@tanstack/react-router";
import { useEffect, type ReactNode } from "react";
import { Toaster } from "sonner";

import appCss from "../styles.css?url";
import { reportLovableError } from "../lib/lovable-error-reporting";

function NotFoundComponent() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--surface)] px-4">
      <div className="max-w-md text-center">
        <h1 className="text-7xl font-bold text-gradient-brand">404</h1>
        <h2 className="mt-4 text-xl font-semibold text-[var(--ink)]">Page not found</h2>
        <p className="mt-2 text-sm text-[var(--muted-foreground)]">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <div className="mt-6">
          <Link
            to="/"
            className="inline-flex items-center justify-center rounded-full bg-[var(--brand-primary)] px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[var(--brand-secondary)]"
          >
            Go home
          </Link>
        </div>
      </div>
    </div>
  );
}

function ErrorComponent({ error, reset }: { error: Error; reset: () => void }) {
  console.error(error);
  const router = useRouter();
  useEffect(() => {
    reportLovableError(error, { boundary: "tanstack_root_error_component" });
  }, [error]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--surface)] px-4">
      <div className="max-w-md text-center">
        <h1 className="text-xl font-semibold tracking-tight text-[var(--ink)]">This page didn't load</h1>
        <p className="mt-2 text-sm text-[var(--muted-foreground)]">
          Something went wrong. Try refreshing or head back home.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <button
            onClick={() => {
              router.invalidate();
              reset();
            }}
            className="inline-flex items-center justify-center rounded-full bg-[var(--brand-primary)] px-5 py-2.5 text-sm font-medium text-white hover:bg-[var(--brand-secondary)]"
          >
            Try again
          </button>
          <a
            href="/"
            className="inline-flex items-center justify-center rounded-full border border-[var(--hairline)] bg-white px-5 py-2.5 text-sm font-medium text-[var(--ink)] hover:border-[var(--brand-secondary)]"
          >
            Go home
          </a>
        </div>
      </div>
    </div>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "Conduit — One wallet. Every AI app." },
      {
        name: "description",
        content:
          "Conduit is a universal prepaid wallet and identity layer for the AI ecosystem. Fund once, connect many apps, pay only for the tokens you use.",
      },
      { name: "author", content: "Conduit" },
      { property: "og:title", content: "Conduit — One wallet. Every AI app." },
      {
        property: "og:description",
        content: "A universal prepaid wallet for AI. Fund once, connect anywhere, pay per token.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
    links: [
      { rel: "stylesheet", href: appCss },
      {
        rel: "icon",
        type: "image/svg+xml",
        href:
          "data:image/svg+xml;utf8," +
          encodeURIComponent(
            `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'><circle cx='42' cy='32' r='14' stroke='%230084FF' stroke-width='6' fill='none'/><circle cx='22' cy='32' r='14' stroke='%230061D5' stroke-width='6' fill='none'/><path d='M42 18 a14 14 0 0 1 12.124 21' stroke='%230084FF' stroke-width='6' fill='none'/></svg>`,
          ),
      },
      {
        rel: "preconnect",
        href: "https://rsms.me",
      },
      {
        rel: "stylesheet",
        href: "https://rsms.me/inter/inter.css",
      },
      {
        rel: "stylesheet",
        href: "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap",
      },
    ],
  }),
  shellComponent: RootShell,
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
  errorComponent: ErrorComponent,
});

function RootShell({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  );
}

function RootComponent() {
  const { queryClient } = Route.useRouteContext();

  return (
    <QueryClientProvider client={queryClient}>
      <Outlet />
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            borderRadius: 12,
            border: "1px solid var(--hairline)",
            background: "white",
            color: "var(--ink)",
          },
        }}
      />
    </QueryClientProvider>
  );
}
