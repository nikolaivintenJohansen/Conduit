import { createFileRoute } from "@tanstack/react-router";
import { useInfiniteQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { formatUsd, formatNumber } from "@/lib/money";
import { formatDateTime } from "@/lib/utils";
import { Button } from "@/components/ui-prim/button";
import { Table, THead, TBody, TR, TH, TD, NumCell } from "@/components/ui-prim/table";

export const Route = createFileRoute("/_authenticated/dashboard/usage")({
  head: () => ({ meta: [{ title: "Usage — Conduit" }] }),
  component: UsagePage,
});

interface UsageRow {
  id: string;
  request_id: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  charged_microdollars: number;
  created_at: string;
}

interface Page {
  data: UsageRow[];
  next_cursor: string | null;
}

function UsagePage() {
  const q = useInfiniteQuery({
    queryKey: ["usage"],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      api<Page>("/wallet/v1/usage", { query: { limit: 20, cursor: pageParam ?? undefined } }),
    getNextPageParam: (last) => last.next_cursor,
  });

  const rows = q.data?.pages.flatMap((p) => p.data) ?? [];

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Usage</h1>
        <p className="text-sm text-[var(--muted-foreground)]">Per-request token usage and cost.</p>
      </div>

      <Table>
        <THead>
          <TR>
            <TH>Time</TH>
            <TH>Model</TH>
            <TH className="text-right">Input</TH>
            <TH className="text-right">Output</TH>
            <TH className="text-right">Cost</TH>
          </TR>
        </THead>
        <TBody>
          {rows.length === 0 && !q.isLoading && (
            <TR>
              <TD colSpan={5} className="text-center py-12 text-[var(--muted-foreground)]">
                No usage yet. Generate an API key and make your first request.
              </TD>
            </TR>
          )}
          {rows.map((r) => (
            <TR key={r.id}>
              <TD className="text-[var(--muted-foreground)]">{formatDateTime(r.created_at)}</TD>
              <TD className="mono">{r.model}</TD>
              <NumCell>{formatNumber(r.input_tokens)}</NumCell>
              <NumCell>{formatNumber(r.output_tokens)}</NumCell>
              <NumCell>{formatUsd(r.charged_microdollars)}</NumCell>
            </TR>
          ))}
        </TBody>
      </Table>

      {q.hasNextPage && (
        <div className="text-center">
          <Button variant="secondary" onClick={() => q.fetchNextPage()} loading={q.isFetchingNextPage}>
            Load more
          </Button>
        </div>
      )}
    </div>
  );
}
