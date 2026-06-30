import { createFileRoute } from "@tanstack/react-router";
import { useInfiniteQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { formatUsd } from "@/lib/money";
import { formatDateTime } from "@/lib/utils";
import { Button } from "@/components/ui-prim/button";
import { Badge } from "@/components/ui-prim/badge";
import { Table, THead, TBody, TR, TH, TD, NumCell } from "@/components/ui-prim/table";

export const Route = createFileRoute("/_authenticated/dashboard/transactions")({
  head: () => ({ meta: [{ title: "Transactions — Conduit" }] }),
  component: TxPage,
});

type EntryType = "DEPOSIT" | "USAGE" | "REFUND" | "SETTLEMENT";

interface Tx {
  id: string;
  entry_type: EntryType;
  amount_microdollars: number;
  balance_after_microdollars: number;
  created_at: string;
}

interface Page {
  data: Tx[];
  next_cursor: string | null;
}

const variantFor: Record<EntryType, "success" | "primary" | "warning" | "muted"> = {
  DEPOSIT: "success",
  USAGE: "primary",
  REFUND: "warning",
  SETTLEMENT: "muted",
};

function TxPage() {
  const q = useInfiniteQuery({
    queryKey: ["transactions"],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      api<Page>("/wallet/v1/wallet/transactions", { query: { limit: 20, cursor: pageParam ?? undefined } }),
    getNextPageParam: (last) => last.next_cursor,
  });

  const rows = q.data?.pages.flatMap((p) => p.data) ?? [];

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Transactions</h1>
        <p className="text-sm text-[var(--muted-foreground)]">Wallet ledger — every credit and debit.</p>
      </div>

      <Table>
        <THead>
          <TR>
            <TH>Time</TH>
            <TH>Type</TH>
            <TH className="text-right">Amount</TH>
            <TH className="text-right">Balance after</TH>
          </TR>
        </THead>
        <TBody>
          {rows.length === 0 && !q.isLoading && (
            <TR>
              <TD colSpan={4} className="text-center py-12 text-[var(--muted-foreground)]">
                No transactions yet.
              </TD>
            </TR>
          )}
          {rows.map((r) => {
            const negative = r.amount_microdollars < 0;
            return (
              <TR key={r.id}>
                <TD className="text-[var(--muted-foreground)]">{formatDateTime(r.created_at)}</TD>
                <TD>
                  <Badge variant={variantFor[r.entry_type]}>{r.entry_type}</Badge>
                </TD>
                <NumCell className={negative ? "text-[var(--destructive)]" : "text-[#0f7c4d]"}>
                  {formatUsd(r.amount_microdollars, { sign: true })}
                </NumCell>
                <NumCell>{formatUsd(r.balance_after_microdollars)}</NumCell>
              </TR>
            );
          })}
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
