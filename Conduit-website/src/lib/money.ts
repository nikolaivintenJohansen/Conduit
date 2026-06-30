export function formatUsd(microdollars: number | null | undefined, opts?: { sign?: boolean }): string {
  const value = typeof microdollars === "number" ? microdollars / 1_000_000 : 0;
  const formatted = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(Math.abs(value));
  if (opts?.sign) {
    if (value > 0) return `+${formatted}`;
    if (value < 0) return `−${formatted}`;
  } else if (value < 0) {
    return `−${formatted}`;
  }
  return formatted;
}

export function toMicro(usd: number): number {
  return Math.round(usd * 1_000_000);
}

export function microToUsdString(microdollars: number): string {
  return (microdollars / 1_000_000).toFixed(2);
}

export function formatNumber(n: number | null | undefined): string {
  if (typeof n !== "number") return "—";
  return new Intl.NumberFormat("en-US").format(n);
}
