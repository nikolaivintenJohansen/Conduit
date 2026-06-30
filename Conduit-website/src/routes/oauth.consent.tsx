import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { z } from "zod";
import { zodValidator, fallback } from "@tanstack/zod-adapter";
import { api } from "@/lib/api";
import { getJwt, setJwt } from "@/lib/auth";
import { Card, CardHeader } from "@/components/ui-prim/card";
import { Field } from "@/components/ui-prim/field";
import { Button } from "@/components/ui-prim/button";
import { Badge } from "@/components/ui-prim/badge";
import { RingMark } from "@/components/ring-mark";
import { Halo } from "@/components/halo";
import { toMicro } from "@/lib/money";

const search = z.object({
  client_id: fallback(z.string(), "").default(""),
  redirect_uri: fallback(z.string(), "").default(""),
  response_type: fallback(z.string(), "code").default("code"),
  state: fallback(z.string(), "").default(""),
  scope: fallback(z.string(), "").default(""),
  code_challenge: fallback(z.string(), "").default(""),
  code_challenge_method: fallback(z.string(), "S256").default("S256"),
  token: fallback(z.string(), "").default(""),
});

export const Route = createFileRoute("/oauth/consent")({
  validateSearch: zodValidator(search),
  head: () => ({ meta: [{ title: "Connect to Conduit" }] }),
  component: ConsentPage,
});

interface Descriptor {
  app_name: string;
  client_id: string;
  requested_scopes: string[];
}

function ConsentPage() {
  const params = Route.useSearch();
  const navigate = useNavigate();

  // Accept token from query (legacy backend flow) and stash to localStorage.
  useEffect(() => {
    if (params.token && !getJwt()) setJwt(params.token);
  }, [params.token]);

  // If still unauthenticated, redirect to /auth and bring them back.
  useEffect(() => {
    if (!getJwt() && typeof window !== "undefined") {
      const here = window.location.pathname + window.location.search;
      navigate({ to: "/auth", search: { tab: "login", redirect: here } });
    }
  }, [navigate]);

  const descriptor = useQuery({
    queryKey: ["oauth-authorize", params.client_id],
    queryFn: () =>
      api<Descriptor>("/oauth/authorize", {
        query: {
          client_id: params.client_id,
          redirect_uri: params.redirect_uri,
          response_type: params.response_type,
          state: params.state,
          scope: params.scope,
          code_challenge: params.code_challenge,
          code_challenge_method: params.code_challenge_method,
        },
      }),
    enabled: !!params.client_id && !!getJwt(),
    retry: false,
  });

  const [capUsd, setCapUsd] = useState("");
  const [resetPeriod, setResetPeriod] = useState<"monthly" | "lifetime">("monthly");

  const approve = useMutation({
    mutationFn: () =>
      api<{ redirect_uri: string }>("/oauth/authorize/consent", {
        method: "POST",
        body: {
          client_id: params.client_id,
          redirect_uri: params.redirect_uri,
          response_type: params.response_type,
          state: params.state,
          scope: params.scope,
          code_challenge: params.code_challenge,
          code_challenge_method: params.code_challenge_method,
          spend_limit_microdollars: capUsd.trim() === "" ? null : toMicro(parseFloat(capUsd)),
          reset_period: resetPeriod,
        },
      }),
    onSuccess: (data) => {
      window.location.href = data.redirect_uri;
    },
  });

  return (
    <div className="min-h-screen flex flex-col bg-[var(--surface)] relative overflow-hidden">
      <Halo />
      <header className="px-6 py-6">
        <RingMark withWordmark size={26} />
      </header>
      <main className="flex-1 flex items-center justify-center px-6 pb-16">
        <Card padding="lg" className="w-full max-w-md">
          {descriptor.isLoading ? (
            <div className="py-12 text-center text-sm text-[var(--muted-foreground)]">Loading…</div>
          ) : descriptor.isError ? (
            <div className="py-12 text-center text-sm text-[var(--destructive)]">
              Couldn't load consent details.
            </div>
          ) : (
            <>
              <CardHeader
                title={`Connect ${descriptor.data?.app_name ?? "app"} to Conduit`}
                subtitle="The app will be able to charge your wallet up to the cap you set below."
              />
              <div className="mb-4">
                <div className="text-xs uppercase tracking-wider text-[var(--muted-foreground)] mb-2">
                  Requested permissions
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {(descriptor.data?.requested_scopes ?? []).map((s) => (
                    <Badge key={s} variant="primary">
                      {s}
                    </Badge>
                  ))}
                </div>
              </div>
              <div className="space-y-4">
                <Field
                  label="Spend cap (USD)"
                  prefix="$"
                  type="number"
                  step="0.01"
                  placeholder="Leave blank for unlimited"
                  value={capUsd}
                  onChange={(e) => setCapUsd(e.target.value)}
                  className="mono"
                />
                <div>
                  <label className="text-sm font-medium">Reset period</label>
                  <select
                    className="mt-1.5 h-11 w-full rounded-lg border border-[var(--hairline)] bg-white px-3 text-sm"
                    value={resetPeriod}
                    onChange={(e) => setResetPeriod(e.target.value as "monthly" | "lifetime")}
                  >
                    <option value="monthly">Monthly</option>
                    <option value="lifetime">Lifetime</option>
                  </select>
                </div>
                <div className="flex gap-2 pt-2">
                  <Button onClick={() => approve.mutate()} loading={approve.isPending} className="flex-1">
                    Approve & connect
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => {
                      if (params.redirect_uri) {
                        const url = new URL(params.redirect_uri);
                        url.searchParams.set("error", "access_denied");
                        if (params.state) url.searchParams.set("state", params.state);
                        window.location.href = url.toString();
                      } else {
                        window.history.back();
                      }
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            </>
          )}
        </Card>
      </main>
    </div>
  );
}
