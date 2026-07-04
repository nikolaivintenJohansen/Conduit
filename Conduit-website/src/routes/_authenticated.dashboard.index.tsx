import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AlertTriangle, Plus, TrendingUp } from "lucide-react";
import { Card, CardHeader } from "@/components/ui-prim/card";
import { Button } from "@/components/ui-prim/button";
import { Field } from "@/components/ui-prim/field";
import { api } from "@/lib/api";
import { formatUsd, toMicro } from "@/lib/money";
import type { MeResponse } from "./_authenticated";

export const Route = createFileRoute("/_authenticated/dashboard/")({
  head: () => ({ meta: [{ title: "Overview — Conduit" }] }),
  component: OverviewPage,
});

const QUICK_PICKS = [5, 10, 25, 50, 100];

function OverviewPage() {
  const me = useQuery({ queryKey: ["me"], queryFn: () => api<MeResponse>("/wallet/v1/me") });
  const wallet = me.data;
  const lowBalance =
    wallet?.low_balance_threshold_microdollars != null &&
    wallet.balance_microdollars <= wallet.low_balance_threshold_microdollars;

  return (
    <div className="space-y-6">
      {lowBalance && (
        <div className="flex items-start gap-3 rounded-xl border border-[#ffe0a3] bg-[#fff8e8] p-4">
          <AlertTriangle className="h-5 w-5 text-[#8a5a00] mt-0.5" />
          <div className="text-sm">
            <div className="font-medium text-[#8a5a00]">Low wallet balance</div>
            <div className="text-[#8a5a00]/80">
              Your balance has fallen below your warning threshold. Add funds to keep connected apps working.
            </div>
          </div>
        </div>
      )}

      <BalanceCard wallet={wallet} loading={me.isLoading} />

      <div className="grid lg:grid-cols-2 gap-6">
        <TopUpCard />
        <SpendControlsCard wallet={wallet} />
      </div>
    </div>
  );
}

function BalanceCard({ wallet, loading }: { wallet?: MeResponse; loading: boolean }) {
  const pct = wallet?.spend_limit_microdollars
    ? Math.min(100, (wallet.monthly_spend_microdollars / wallet.spend_limit_microdollars) * 100)
    : 0;
  return (
    <Card padding="lg" className="relative overflow-hidden">
      <div className="absolute -top-24 -right-24 h-72 w-72 rounded-full bg-gradient-brand opacity-10 blur-3xl pointer-events-none" />
      <div className="relative">
        <div className="text-xs uppercase tracking-wider text-[var(--muted-foreground)]">Wallet balance</div>
        <div className="mt-2 mono text-6xl font-semibold tracking-tight text-[var(--ink)]">
          {loading ? "—" : formatUsd(wallet?.balance_microdollars ?? 0)}
        </div>
        <div className="mt-2 text-sm text-[var(--muted-foreground)]">
          Available <span className="mono text-[var(--ink)]">{formatUsd(wallet?.available_microdollars ?? 0)}</span>
          {"  ·  "}Held <span className="mono text-[var(--ink)]">{formatUsd(wallet?.held_microdollars ?? 0)}</span>
        </div>

        <div className="mt-6 pt-6 border-t border-[var(--hairline)] flex items-center gap-4">
          <TrendingUp className="h-4 w-4 text-[var(--brand-primary)]" />
          <div className="flex-1">
            <div className="flex items-center justify-between text-sm">
              <span className="text-[var(--muted-foreground)]">Monthly spend</span>
              <span className="mono text-[var(--ink)]">
                {formatUsd(wallet?.monthly_spend_microdollars ?? 0)}
                {wallet?.spend_limit_microdollars
                  ? ` / ${formatUsd(wallet.spend_limit_microdollars)}`
                  : " · unlimited"}
              </span>
            </div>
            {wallet?.spend_limit_microdollars && (
              <div className="mt-2 h-1.5 w-full rounded-full bg-[var(--surface-alt)] overflow-hidden">
                <div className="h-full bg-gradient-brand" style={{ width: `${pct}%` }} />
              </div>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}

function TopUpCard() {
  const [usd, setUsd] = useState("10.00");

  const mutation = useMutation({
    mutationFn: async () => {
      const amount_microdollars = toMicro(parseFloat(usd));
      return api<{ checkout_url: string; payment_intent_id: string }>("/wallet/v1/topups/checkout", {
        method: "POST",
        body: { amount_microdollars },
      });
    },
    onSuccess: (data) => {
      window.location.href = data.checkout_url;
    },
  });

  const valid = parseFloat(usd) >= 0.5;

  return (
    <Card padding="lg">
      <CardHeader title="Add funds" subtitle="Top up your prepaid balance via Stripe." />
      <div className="flex flex-wrap gap-2 mb-4">
        {QUICK_PICKS.map((v) => (
          <button
            key={v}
            onClick={() => setUsd(v.toFixed(2))}
            className={`mono rounded-full border px-3 py-1 text-sm transition-colors ${
              parseFloat(usd) === v
                ? "border-[var(--brand-primary)] bg-[#eaf2ff] text-[var(--brand-primary)]"
                : "border-[var(--hairline)] hover:border-[var(--brand-secondary)]"
            }`}
          >
            ${v}
          </button>
        ))}
      </div>
      <Field
        prefix="$"
        value={usd}
        onChange={(e) => setUsd(e.target.value)}
        type="number"
        step="0.01"
        min="0.5"
        hint="Minimum $0.50"
        className="mono"
      />
      <div className="mt-4">
        <Button onClick={() => mutation.mutate()} disabled={!valid} loading={mutation.isPending} className="w-full">
          <Plus className="h-4 w-4" /> Continue to checkout
        </Button>
      </div>
    </Card>
  );
}

function SpendControlsCard({ wallet }: { wallet?: MeResponse }) {
  const qc = useQueryClient();
  const [limit, setLimit] = useState("");
  const [threshold, setThreshold] = useState("");

  // Keep input in sync once data arrives.
  if (wallet && limit === "" && wallet.spend_limit_microdollars != null) {
    setLimit((wallet.spend_limit_microdollars / 1_000_000).toFixed(2));
  }
  if (wallet && threshold === "" && wallet.low_balance_threshold_microdollars != null) {
    setThreshold((wallet.low_balance_threshold_microdollars / 1_000_000).toFixed(2));
  }

  const mutation = useMutation({
    mutationFn: async () =>
      api<MeResponse>("/wallet/v1/wallet/settings", {
        method: "PATCH",
        body: {
          spend_limit_microdollars: limit.trim() === "" ? null : toMicro(parseFloat(limit)),
          low_balance_threshold_microdollars: threshold.trim() === "" ? null : toMicro(parseFloat(threshold)),
        },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["me"] });
      qc.invalidateQueries({ queryKey: ["wallet"] });
    },
  });

  return (
    <Card padding="lg">
      <CardHeader title="Spend controls" subtitle="Set a monthly cap and a low-balance warning." />
      <div className="space-y-4">
        <Field
          label="Monthly spend cap"
          prefix="$"
          value={limit}
          onChange={(e) => setLimit(e.target.value)}
          type="number"
          step="0.01"
          placeholder="Leave blank for unlimited"
          className="mono"
        />
        <Field
          label="Low-balance warning"
          prefix="$"
          value={threshold}
          onChange={(e) => setThreshold(e.target.value)}
          type="number"
          step="0.01"
          placeholder="e.g. 5.00"
          className="mono"
        />
        <Button onClick={() => mutation.mutate()} loading={mutation.isPending} className="w-full">
          Save settings
        </Button>
      </div>
    </Card>
  );
}
