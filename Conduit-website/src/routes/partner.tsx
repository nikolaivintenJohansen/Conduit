import { createFileRoute, Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Plus, RotateCw, Trash2, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";
import { usePartner } from "@/lib/auth";
import { Button } from "@/components/ui-prim/button";
import { Card, CardHeader } from "@/components/ui-prim/card";
import { Field } from "@/components/ui-prim/field";
import { Badge } from "@/components/ui-prim/badge";
import { DarkCodeBlock } from "@/components/ui-prim/dark-code-block";
import { RingMark } from "@/components/ring-mark";

export const Route = createFileRoute("/partner")({
  head: () => ({ meta: [{ title: "Partner — Conduit" }] }),
  component: PartnerPage,
});

interface PartnerApp {
  id: string;
  client_id: string;
  app_name: string;
  redirect_uris: string[];
  is_active: boolean;
  created_at: string;
}

function PartnerPage() {
  const { slug, isConfigured } = usePartner();
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [revealedSecret, setRevealedSecret] = useState<string | null>(null);

  const apps = useQuery({
    queryKey: ["partner-apps", slug],
    queryFn: () => api<{ data: PartnerApp[] }>(`/wallet/v1/partner/${slug}/apps`, { partner: true }),
    enabled: isConfigured,
    retry: false,
  });

  const rotate = useMutation({
    mutationFn: (id: string) =>
      api<{ client_secret: string }>(`/wallet/v1/partner/${slug}/apps/${id}/rotate-secret`, {
        method: "POST",
        partner: true,
      }),
    onSuccess: (data) => setRevealedSecret(data.client_secret),
  });

  const deactivate = useMutation({
    mutationFn: (id: string) =>
      api(`/wallet/v1/partner/${slug}/apps/${id}`, { method: "DELETE", partner: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["partner-apps"] }),
  });

  if (!isConfigured) {
    return (
      <div className="min-h-screen bg-[var(--surface-alt)] flex items-center justify-center p-6">
        <Card padding="lg" className="max-w-md w-full text-center">
          <RingMark size={40} className="mx-auto" />
          <h1 className="mt-4 text-2xl font-semibold tracking-tight">Partner mode required</h1>
          <p className="mt-2 text-sm text-[var(--muted-foreground)]">
            Configure your partner slug and admin token in Settings to manage OAuth clients.
          </p>
          <div className="mt-6">
            <Link to="/dashboard/settings">
              <Button>Open settings</Button>
            </Link>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--surface-alt)]">
      <header className="h-16 bg-white border-b border-[var(--hairline)] flex items-center justify-between px-6">
        <Link to="/">
          <RingMark withWordmark size={26} />
        </Link>
        <div className="text-sm text-[var(--muted-foreground)]">
          Partner: <span className="mono text-[var(--ink)]">{slug}</span>
        </div>
      </header>
      <main className="max-w-5xl mx-auto p-6 md:p-8 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">OAuth clients</h1>
            <p className="text-sm text-[var(--muted-foreground)]">Apps you've registered for end-user wallet connections.</p>
          </div>
          <Button onClick={() => setShowCreate((s) => !s)}>
            <Plus className="h-4 w-4" /> Register app
          </Button>
        </div>

        {revealedSecret && (
          <Card padding="lg">
            <div className="flex items-start gap-3 mb-3">
              <AlertTriangle className="h-5 w-5 text-[#8a5a00] mt-0.5" />
              <div>
                <div className="font-medium">Save this client secret — it won't be shown again.</div>
              </div>
            </div>
            <DarkCodeBlock code={revealedSecret} />
            <div className="mt-3 text-right">
              <Button variant="ghost" size="sm" onClick={() => setRevealedSecret(null)}>
                I've saved it
              </Button>
            </div>
          </Card>
        )}

        {showCreate && (
          <CreateAppForm
            slug={slug!}
            onCreated={(secret) => {
              setRevealedSecret(secret);
              setShowCreate(false);
              qc.invalidateQueries({ queryKey: ["partner-apps"] });
            }}
            onCancel={() => setShowCreate(false)}
          />
        )}

        <div className="space-y-4">
          {apps.data?.data.length === 0 && (
            <Card className="text-center py-12 text-[var(--muted-foreground)]">No apps registered yet.</Card>
          )}
          {apps.data?.data.map((app) => (
            <Card key={app.id}>
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div>
                  <div className="flex items-center gap-2">
                    <div className="font-semibold">{app.app_name}</div>
                    {app.is_active ? (
                      <Badge variant="primary">Active</Badge>
                    ) : (
                      <Badge variant="muted">Inactive</Badge>
                    )}
                  </div>
                  <div className="mono text-xs text-[var(--muted-foreground)] mt-1">{app.client_id}</div>
                  <div className="text-xs text-[var(--muted-foreground)] mt-1">
                    Redirects: {app.redirect_uris.join(", ")}
                  </div>
                </div>
                {app.is_active && (
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => rotate.mutate(app.id)}
                      className="p-2 rounded-md hover:bg-[var(--surface-alt)]"
                      title="Rotate secret"
                    >
                      <RotateCw className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => {
                        if (confirm(`Deactivate ${app.app_name}?`)) deactivate.mutate(app.id);
                      }}
                      className="p-2 rounded-md hover:bg-[var(--surface-alt)] text-[var(--destructive)]"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                )}
              </div>
            </Card>
          ))}
        </div>
      </main>
    </div>
  );
}

function CreateAppForm({
  slug,
  onCreated,
  onCancel,
}: {
  slug: string;
  onCreated: (secret: string) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [redirects, setRedirects] = useState("");

  const create = useMutation({
    mutationFn: () =>
      api<{ client_id: string; client_secret: string }>(`/wallet/v1/partner/${slug}/apps`, {
        method: "POST",
        partner: true,
        body: {
          app_name: name,
          redirect_uris: redirects.split(/[\s,]+/).filter(Boolean),
        },
      }),
    onSuccess: (data) => onCreated(data.client_secret),
  });

  return (
    <Card padding="lg">
      <CardHeader title="Register a new OAuth client" />
      <div className="space-y-4">
        <Field label="App name" value={name} onChange={(e) => setName(e.target.value)} required />
        <Field
          label="Redirect URIs"
          value={redirects}
          onChange={(e) => setRedirects(e.target.value)}
          placeholder="https://yourapp.com/cb"
          hint="Comma- or whitespace-separated."
          className="mono"
        />
        <div className="flex gap-2">
          <Button onClick={() => create.mutate()} loading={create.isPending} disabled={!name || !redirects}>
            Create
          </Button>
          <Button variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        </div>
      </div>
    </Card>
  );
}
