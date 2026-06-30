import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui-prim/button";
import { Card } from "@/components/ui-prim/card";
import { Field } from "@/components/ui-prim/field";
import { Badge } from "@/components/ui-prim/badge";
import { formatUsd, toMicro } from "@/lib/money";
import { formatDateTime } from "@/lib/utils";

export const Route = createFileRoute("/_authenticated/dashboard/apps")({
  head: () => ({ meta: [{ title: "Connected Apps — Conduit" }] }),
  component: AppsPage,
});

interface App {
  install_id: string;
  client_id: string;
  app_name: string;
  display_name?: string;
  spend_limit_microdollars: number | null;
  allowance_spent_microdollars: number;
  allowance_reset_period: "monthly" | "lifetime";
  consented_at: string;
  revoked_at: string | null;
}

function AppsPage() {
  const qc = useQueryClient();
  const apps = useQuery({ queryKey: ["apps"], queryFn: () => api<{ data: App[] }>("/wallet/v1/apps") });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Connected apps</h1>
        <p className="text-sm text-[var(--muted-foreground)]">
          Apps with permission to charge your wallet. Edit caps or revoke instantly.
        </p>
      </div>

      <div className="space-y-4">
        {apps.data?.data.length === 0 && (
          <Card className="text-center py-12 text-[var(--muted-foreground)]">
            No connected apps yet. When a partner app sends you to Conduit, you'll see it here.
          </Card>
        )}
        {apps.data?.data.map((app) => (
          <AppRow key={app.install_id} app={app} onChange={() => qc.invalidateQueries({ queryKey: ["apps"] })} />
        ))}
      </div>
    </div>
  );
}

function AppRow({ app, onChange }: { app: App; onChange: () => void }) {
  const [editing, setEditing] = useState(false);
  const [cap, setCap] = useState(
    app.spend_limit_microdollars != null ? (app.spend_limit_microdollars / 1_000_000).toFixed(2) : "",
  );

  const update = useMutation({
    mutationFn: () =>
      api(`/wallet/v1/apps/${app.install_id}`, {
        method: "PATCH",
        body: {
          spend_limit_microdollars: cap.trim() === "" ? null : toMicro(parseFloat(cap)),
        },
      }),
    onSuccess: () => {
      setEditing(false);
      onChange();
    },
  });

  const revoke = useMutation({
    mutationFn: () => api(`/wallet/v1/apps/${app.install_id}`, { method: "DELETE" }),
    onSuccess: onChange,
  });

  const pct =
    app.spend_limit_microdollars && app.spend_limit_microdollars > 0
      ? Math.min(100, (app.allowance_spent_microdollars / app.spend_limit_microdollars) * 100)
      : 0;

  return (
    <Card hoverable={!app.revoked_at}>
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex-1 min-w-[200px]">
          <div className="flex items-center gap-2">
            <div className="font-semibold">{app.display_name ?? app.app_name}</div>
            {app.revoked_at ? (
              <Badge variant="muted">Revoked</Badge>
            ) : (
              <Badge variant="primary">{app.allowance_reset_period}</Badge>
            )}
          </div>
          <div className="mono text-xs text-[var(--muted-foreground)] mt-1">{app.client_id}</div>
          <div className="text-xs text-[var(--muted-foreground)] mt-1">Connected {formatDateTime(app.consented_at)}</div>
        </div>
        <div className="flex-1 min-w-[240px]">
          <div className="flex items-center justify-between text-sm mb-1.5">
            <span className="text-[var(--muted-foreground)]">Spent this period</span>
            <span className="mono text-[var(--ink)]">
              {formatUsd(app.allowance_spent_microdollars)}
              {app.spend_limit_microdollars != null
                ? ` / ${formatUsd(app.spend_limit_microdollars)}`
                : " · unlimited"}
            </span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-[var(--surface-alt)] overflow-hidden">
            <div className="h-full bg-gradient-brand" style={{ width: `${pct}%` }} />
          </div>
        </div>
        {!app.revoked_at && (
          <div className="flex items-center gap-2">
            <Button size="sm" variant="secondary" onClick={() => setEditing((e) => !e)}>
              Edit cap
            </Button>
            <button
              onClick={() => {
                if (confirm(`Revoke ${app.app_name}? It will stop charging immediately.`)) revoke.mutate();
              }}
              className="p-2 rounded-md text-[var(--destructive)] hover:bg-[var(--surface-alt)]"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>

      {editing && (
        <div className="mt-4 pt-4 border-t border-[var(--hairline)] flex items-end gap-2">
          <div className="flex-1">
            <Field
              label="Spend cap"
              prefix="$"
              value={cap}
              onChange={(e) => setCap(e.target.value)}
              placeholder="Leave blank for unlimited"
              type="number"
              step="0.01"
              className="mono"
            />
          </div>
          <Button onClick={() => update.mutate()} loading={update.isPending}>
            Save
          </Button>
        </div>
      )}
    </Card>
  );
}
