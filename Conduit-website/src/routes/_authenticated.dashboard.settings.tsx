import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Card, CardHeader } from "@/components/ui-prim/card";
import { Field } from "@/components/ui-prim/field";
import { Button } from "@/components/ui-prim/button";
import { Badge } from "@/components/ui-prim/badge";
import { api } from "@/lib/api";
import { clearPartner, getPartnerSlug, getPartnerToken, setPartnerToken } from "@/lib/auth";
import type { MeResponse } from "./_authenticated";

export const Route = createFileRoute("/_authenticated/dashboard/settings")({
  head: () => ({ meta: [{ title: "Settings — Conduit" }] }),
  component: SettingsPage,
});

function SettingsPage() {
  const me = useQuery({ queryKey: ["me"], queryFn: () => api<MeResponse>("/wallet/v1/me") });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-[var(--muted-foreground)]">Profile and partner admin tokens.</p>
      </div>

      <Card padding="lg">
        <CardHeader title="Profile" />
        <div className="grid md:grid-cols-2 gap-4">
          <Field label="Email" value={me.data?.email ?? ""} readOnly disabled />
          <Field label="Display name" value={me.data?.display_name ?? ""} readOnly disabled />
          <Field label="Wallet ID" value={me.data?.wallet_id ?? ""} readOnly disabled className="mono text-xs" />
          <Field label="Currency" value={me.data?.currency ?? "USD"} readOnly disabled />
        </div>
      </Card>

      <PartnerModeCard />
    </div>
  );
}

function PartnerModeCard() {
  const [token, setTokenState] = useState(getPartnerToken() ?? "");
  const [slug, setSlugState] = useState(getPartnerSlug() ?? "");
  const configured = !!(getPartnerToken() && getPartnerSlug());

  return (
    <Card padding="lg">
      <CardHeader
        title="Partner mode"
        subtitle="Paste your X-Partner-Admin-Token to manage OAuth clients for your partner organization."
        action={configured ? <Badge variant="primary">Configured</Badge> : <Badge variant="muted">Not set</Badge>}
      />
      <div className="space-y-4">
        <Field
          label="Partner slug"
          value={slug}
          onChange={(e) => setSlugState(e.target.value)}
          placeholder="acme-ai"
          className="mono"
        />
        <Field
          label="Partner admin token"
          value={token}
          onChange={(e) => setTokenState(e.target.value)}
          type="password"
          placeholder="ptk_..."
          className="mono"
        />
        <div className="flex gap-2">
          <Button onClick={() => setPartnerToken(token, slug)} disabled={!token || !slug}>
            Save
          </Button>
          <Button
            variant="ghost"
            onClick={() => {
              clearPartner();
              setTokenState("");
              setSlugState("");
            }}
          >
            Clear
          </Button>
        </div>
        <p className="text-xs text-[var(--muted-foreground)]">
          Stored locally in your browser as <code className="mono">uaw_partner_token</code>. Cleared on sign out.
        </p>
      </div>
    </Card>
  );
}
