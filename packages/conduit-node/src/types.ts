import type { ConduitError } from './errors.js';

export type FetchLike = typeof fetch;

export interface ConduitConfig {
  /** Bearer credential: an sk-conduit-* virtual key OR a delegated OAuth app access token. */
  apiKey: string;
  /** Gateway base URL including the /v1 prefix. Default: https://api.example.com/v1 */
  baseUrl?: string;
  /** Periodic flush interval for batched charge() events (ms). Default: 5000. Set 0 to disable timer. */
  flushIntervalMs?: number;
  /** Flush trigger when the in-memory buffer reaches this many events. Default: 100. */
  maxBatchSize?: number;
  /** Hard cap on buffered events; oldest are dropped via onDrop when exceeded. Default: 10000. */
  maxBufferSize?: number;
  /** Per-request HTTP timeout (ms). Default: 10000. */
  timeoutMs?: number;
  /** Number of retry attempts for a failing usage flush (exponential backoff). Default: 3. */
  retries?: number;
  /** Injectable fetch (Node 18+ global, browser, edge, tests). */
  fetch?: FetchLike;
  /** Optional structured logger; silent by default. */
  logger?: Logger;
  /** Called when buffered events are dropped due to backpressure. */
  onDrop?: (events: UsageEvent[], reason: 'buffer_full' | 'max_retries') => void;
  /** Called when a flush attempt fails after exhausting retries. */
  onError?: (error: ConduitError, context: { events: UsageEvent[] }) => void;
}

export interface Logger {
  debug?(msg: string, data?: Record<string, unknown>): void;
  info?(msg: string, data?: Record<string, unknown>): void;
  warn?(msg: string, data?: Record<string, unknown>): void;
  error?(msg: string, data?: Record<string, unknown>): void;
}

export interface AuthorizeOptions {
  model: string;
  maxTokens?: number;
  /** Optional explicit reserve in microdollars ($1 = 1_000_000) instead of an estimate. */
  requestedReserveMicrodollars?: number;
  /** Optional idempotency / tracing id; generated if absent. */
  requestId?: string;
}

export interface AuthorizeResult {
  authorized: boolean;
  requestId: string;
  mode: string;
  heldMicrodollars: number;
  availableMicrodollars: number;
  balanceMicrodollars: number;
  expiresAtMs?: number | null;
}

export interface ChargeInput {
  /** Must match the requestId returned by authorize() so the worker can release the hold. */
  requestId: string;
  model: string;
  inputTokens?: number;
  outputTokens?: number;
  provider?: string;
}

export interface UsageEvent {
  requestId: string;
  model: string;
  inputTokens: number;
  outputTokens: number;
  provider?: string;
}

export interface UsageIngestResult {
  accepted: number;
  duplicated: number;
  stream: string;
  requestIds: string[];
}
