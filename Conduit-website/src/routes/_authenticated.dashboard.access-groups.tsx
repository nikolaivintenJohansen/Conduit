import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui-prim/button";
import { Card, CardHeader } from "@/components/ui-prim/card";
import { Field } from "@/components/ui-prim/field";
import { Badge } from "@/components/ui-prim/badge";
import { formatDateTime } from "@/lib/utils";

export const Route = createFileRoute("/_authenticated/dashboard/access-groups")({
  head: () => ({ meta: [{ title: "Access Groups — Conduit" }] }),
  component: AccessGroupsPage,
});

interface Model {
  id: string;
  slug: string;
  display_name: string;
  provider: string;
}

interface Group {
  id: string;
  name: string;
  description?: string;
  model_slugs: string[];
  created_at: string;
}

function AccessGroupsPage() {
  const qc = useQueryClient();
  const models = useQuery({ queryKey: ["models"], queryFn: () => api<{ data: Model[] }>("/wallet/v1/models") });
  const groups = useQuery({
    queryKey: ["access-groups"],
    queryFn: () => api<{ data: Group[] }>("/wallet/v1/access-groups"),
  });

  const [editing, setEditing] = useState<Group | null>(null);
  const [creating, setCreating] = useState(false);

  function close() {
    setEditing(null);
    setCreating(false);
  }

  const del = useMutation({
    mutationFn: (id: string) => api(`/wallet/v1/access-groups/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["access-groups"] }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Access groups</h1>
          <p className="text-sm text-[var(--muted-foreground)]">Bundle models, then gate API keys to a group.</p>
        </div>
        <Button onClick={() => setCreating(true)}>
          <Plus className="h-4 w-4" /> New group
        </Button>
      </div>

      {(creating || editing) && (
        <GroupForm
          allModels={models.data?.data ?? []}
          initial={editing}
          onDone={() => {
            close();
            qc.invalidateQueries({ queryKey: ["access-groups"] });
          }}
          onCancel={close}
        />
      )}

      <div className="grid md:grid-cols-2 gap-4">
        {groups.data?.data.length === 0 && (
          <Card className="md:col-span-2 text-center py-12 text-[var(--muted-foreground)]">
            No access groups yet.
          </Card>
        )}
        {groups.data?.data.map((g) => (
          <Card key={g.id} hoverable>
            <div className="flex items-start justify-between">
              <div>
                <div className="font-semibold">{g.name}</div>
                {g.description && (
                  <div className="text-sm text-[var(--muted-foreground)] mt-1">{g.description}</div>
                )}
              </div>
              <div className="flex items-center gap-1">
                <Button size="sm" variant="ghost" onClick={() => setEditing(g)}>
                  Edit
                </Button>
                <button
                  onClick={() => {
                    if (confirm(`Delete "${g.name}"?`)) del.mutate(g.id);
                  }}
                  className="p-1.5 rounded-md hover:bg-[var(--surface-alt)] text-[var(--destructive)]"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-1.5">
              {g.model_slugs.map((s) => (
                <Badge key={s} variant="primary">
                  {s}
                </Badge>
              ))}
            </div>
            <div className="mt-4 text-xs text-[var(--muted-foreground)]">Created {formatDateTime(g.created_at)}</div>
          </Card>
        ))}
      </div>
    </div>
  );
}

function GroupForm({
  initial,
  allModels,
  onDone,
  onCancel,
}: {
  initial?: Group | null;
  allModels: Model[];
  onDone: () => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [selected, setSelected] = useState<string[]>(initial?.model_slugs ?? []);

  const save = useMutation({
    mutationFn: () =>
      initial
        ? api(`/wallet/v1/access-groups/${initial.id}`, {
            method: "PATCH",
            body: { name, description, model_slugs: selected },
          })
        : api(`/wallet/v1/access-groups`, {
            method: "POST",
            body: { name, description, model_slugs: selected },
          }),
    onSuccess: onDone,
  });

  return (
    <Card padding="lg">
      <CardHeader title={initial ? "Edit access group" : "New access group"} />
      <div className="space-y-4">
        <Field label="Name" value={name} onChange={(e) => setName(e.target.value)} required />
        <Field label="Description" value={description} onChange={(e) => setDescription(e.target.value)} />
        <div>
          <label className="text-sm font-medium">Models</label>
          <div className="mt-1.5 max-h-64 overflow-y-auto rounded-lg border border-[var(--hairline)] p-2 space-y-1">
            {allModels.map((m) => {
              const checked = selected.includes(m.slug);
              return (
                <label
                  key={m.id}
                  className="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-[var(--surface-alt)] cursor-pointer"
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(e) => {
                      setSelected((prev) =>
                        e.target.checked ? [...prev, m.slug] : prev.filter((s) => s !== m.slug),
                      );
                    }}
                  />
                  <span className="text-sm">{m.display_name}</span>
                  <span className="mono text-xs text-[var(--muted-foreground)] ml-auto">{m.slug}</span>
                </label>
              );
            })}
            {allModels.length === 0 && (
              <div className="px-2 py-4 text-sm text-[var(--muted-foreground)] text-center">No models available.</div>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!name}>
            {initial ? "Save changes" : "Create group"}
          </Button>
          <Button variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        </div>
      </div>
    </Card>
  );
}
