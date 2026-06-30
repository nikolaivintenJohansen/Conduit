import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AlertTriangle, Plus, RotateCw, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui-prim/button";
import { Card, CardHeader } from "@/components/ui-prim/card";
import { Field } from "@/components/ui-prim/field";
import { Badge } from "@/components/ui-prim/badge";
import { DarkCodeBlock } from "@/components/ui-prim/dark-code-block";
import { formatDateTime } from "@/lib/utils";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui-prim/table";

export const Route = createFileRoute("/_authenticated/dashboard/keys")({
  head: () => ({ meta: [{ title: "API Keys — Conduit" }] }),
  component: KeysPage,
});

interface Key {
  id: string;
  name?: string;
  key_prefix: string;
  rpm_limit: number;
  tpm_limit: number;
  access_group_id: string | null;
  created_at: string;
  revoked_at: string | null;
}

interface AccessGroup {
  id: string;
  name: string;
}

function KeysPage() {
  const qc = useQueryClient();
  const keys = useQuery({
    queryKey: ["keys"],
    queryFn: () => api<{ data: Key[] }>("/wallet/v1/keys"),
  });
  const groups = useQuery({
    queryKey: ["access-groups"],
    queryFn: () => api<{ data: AccessGroup[] }>("/wallet/v1/access-groups"),
  });

  const [showCreate, setShowCreate] = useState(false);
  const [newKeyPlain, setNewKeyPlain] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [groupId, setGroupId] = useState<string>("");

  const create = useMutation({
    mutationFn: () =>
      api<Key & { key: string }>("/wallet/v1/keys", {
        method: "POST",
        body: {
          name: name || undefined,
          rpm_limit: 60,
          tpm_limit: 100000,
          access_group_id: groupId || undefined,
        },
      }),
    onSuccess: (data) => {
      setNewKeyPlain(data.key);
      setShowCreate(false);
      setName("");
      setGroupId("");
      qc.invalidateQueries({ queryKey: ["keys"] });
    },
  });

  const rotate = useMutation({
    mutationFn: (id: string) => api<{ key: string }>(`/wallet/v1/keys/${id}/rotate`, { method: "POST" }),
    onSuccess: (data) => {
      setNewKeyPlain(data.key);
      qc.invalidateQueries({ queryKey: ["keys"] });
    },
  });

  const revoke = useMutation({
    mutationFn: (id: string) => api(`/wallet/v1/keys/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["keys"] }),
  });

  const updateGroup = useMutation({
    mutationFn: (args: { id: string; access_group_id: string | null }) =>
      api(`/wallet/v1/keys/${args.id}`, {
        method: "PATCH",
        body: { access_group_id: args.access_group_id },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["keys"] }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">API keys</h1>
          <p className="text-sm text-[var(--muted-foreground)]">Issue keys scoped to model access groups.</p>
        </div>
        <Button onClick={() => setShowCreate((s) => !s)}>
          <Plus className="h-4 w-4" /> New key
        </Button>
      </div>

      {newKeyPlain && (
        <Card padding="lg">
          <div className="flex items-start gap-3 mb-3">
            <AlertTriangle className="h-5 w-5 text-[#8a5a00] mt-0.5" />
            <div>
              <div className="font-medium">Save this key — it won't be shown again.</div>
              <p className="text-sm text-[var(--muted-foreground)]">
                Treat it like a password. If you lose it, rotate the key.
              </p>
            </div>
          </div>
          <DarkCodeBlock code={newKeyPlain} />
          <div className="mt-3 text-right">
            <Button variant="ghost" size="sm" onClick={() => setNewKeyPlain(null)}>
              I've saved it
            </Button>
          </div>
        </Card>
      )}

      {showCreate && (
        <Card padding="lg">
          <CardHeader title="Create API key" />
          <div className="grid md:grid-cols-2 gap-4">
            <Field label="Name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Production server" />
            <div>
              <label className="text-sm font-medium">Access group</label>
              <select
                value={groupId}
                onChange={(e) => setGroupId(e.target.value)}
                className="mt-1.5 h-11 w-full rounded-lg border border-[var(--hairline)] bg-white px-3 text-sm"
              >
                <option value="">All models (default)</option>
                {groups.data?.data.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="mt-4 flex gap-2">
            <Button onClick={() => create.mutate()} loading={create.isPending}>
              Create key
            </Button>
            <Button variant="ghost" onClick={() => setShowCreate(false)}>
              Cancel
            </Button>
          </div>
        </Card>
      )}

      <Table>
        <THead>
          <TR>
            <TH>Name</TH>
            <TH>Key</TH>
            <TH>Access group</TH>
            <TH>Rate limits</TH>
            <TH>Created</TH>
            <TH></TH>
          </TR>
        </THead>
        <TBody>
          {keys.data?.data.length === 0 && (
            <TR>
              <TD colSpan={6} className="text-center py-12 text-[var(--muted-foreground)]">
                No API keys yet.
              </TD>
            </TR>
          )}
          {keys.data?.data.map((k) => (
            <TR key={k.id}>
              <TD className="font-medium">{k.name ?? "—"}</TD>
              <TD className="mono text-[var(--muted-foreground)]">{k.key_prefix}…</TD>
              <TD>
                <select
                  value={k.access_group_id ?? ""}
                  onChange={(e) =>
                    updateGroup.mutate({ id: k.id, access_group_id: e.target.value || null })
                  }
                  disabled={!!k.revoked_at}
                  className="text-sm rounded-md border border-[var(--hairline)] px-2 py-1 bg-white"
                >
                  <option value="">All models</option>
                  {groups.data?.data.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name}
                    </option>
                  ))}
                </select>
              </TD>
              <TD className="mono text-xs text-[var(--muted-foreground)]">
                {k.rpm_limit} rpm · {k.tpm_limit} tpm
              </TD>
              <TD className="text-[var(--muted-foreground)] text-xs">{formatDateTime(k.created_at)}</TD>
              <TD>
                {k.revoked_at ? (
                  <Badge variant="muted">Revoked</Badge>
                ) : (
                  <div className="flex items-center justify-end gap-1">
                    <button
                      onClick={() => rotate.mutate(k.id)}
                      className="p-1.5 rounded-md hover:bg-[var(--surface-alt)]"
                      title="Rotate"
                    >
                      <RotateCw className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => {
                        if (confirm("Revoke this key? It will stop working immediately.")) revoke.mutate(k.id);
                      }}
                      className="p-1.5 rounded-md hover:bg-[var(--surface-alt)] text-[var(--destructive)]"
                      title="Revoke"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                )}
              </TD>
            </TR>
          ))}
        </TBody>
      </Table>
    </div>
  );
}
