import { AIWalletError } from './errors.js';
import { isRetriable } from './transport.js';
import type { Logger, UsageEvent, UsageIngestResult } from './types.js';

export interface UsageEventDto {
  request_id: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  provider?: string;
}

export type UsageSender = (events: UsageEventDto[]) => Promise<UsageIngestResult>;

export interface BatcherOptions {
  flushIntervalMs: number;
  maxBatchSize: number;
  maxBufferSize: number;
  retries: number;
  logger?: Logger;
  onDrop?: (events: UsageEvent[], reason: 'buffer_full' | 'max_retries') => void;
  onError?: (error: AIWalletError, context: { events: UsageEvent[] }) => void;
  /** Injectable sleep for deterministic tests. */
  sleep?: (ms: number) => Promise<void>;
  /** Injectable timer factory for deterministic tests. */
  setInterval?: (handler: () => void, ms: number) => ReturnType<typeof setInterval>;
  clearInterval?: (id: ReturnType<typeof setInterval>) => void;
}

const DEFAULT_SLEEP = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

function backoffMs(attempt: number): number {
  const base = 500 * 2 ** attempt;
  const capped = Math.min(base, 30_000);
  // Add +-10% jitter.
  const jitter = Math.round(capped * 0.1 * (Math.random() * 2 - 1));
  return Math.max(0, capped + jitter);
}

function toDto(event: UsageEvent): UsageEventDto {
  const dto: UsageEventDto = {
    request_id: event.requestId,
    model: event.model,
    input_tokens: event.inputTokens,
    output_tokens: event.outputTokens,
  };
  if (event.provider !== undefined) dto.provider = event.provider;
  return dto;
}

function ensureError(err: unknown): AIWalletError {
  if (err instanceof AIWalletError) return err;
  return new AIWalletError(`Flush failed: ${String(err)}`, { code: 'flush_error', status: 0 });
}

/**
 * Phase 6.3 — in-memory, fire-and-forget usage batcher. `add()` is synchronous
 * and never blocks the caller. Events are flushed to POST /v1/usage on an
 * interval, when the buffer reaches `maxBatchSize`, or on explicit `flush()` /
 * `shutdown()`. Failures retry with exponential backoff; after `retries`
 * attempts the batch is dropped and `onError`/`onDrop` are notified.
 */
export class UsageBatcher {
  private readonly buffer = new Map<string, UsageEvent>();
  private readonly orderedIds: string[] = [];
  private timer: ReturnType<typeof setInterval> | null = null;
  private flushInFlight: Promise<void> | null = null;
  private stopped = false;

  private readonly send: UsageSender;
  private readonly flushIntervalMs: number;
  private readonly maxBatchSize: number;
  private readonly maxBufferSize: number;
  private readonly retries: number;
  private readonly logger?: Logger;
  private readonly onDrop?: BatcherOptions['onDrop'];
  private readonly onError?: BatcherOptions['onError'];
  private readonly sleep: (ms: number) => Promise<void>;
  private readonly setIntervalFn: (handler: () => void, ms: number) => ReturnType<typeof setInterval>;
  private readonly clearIntervalFn: (id: ReturnType<typeof setInterval>) => void;

  constructor(send: UsageSender, options: BatcherOptions) {
    this.send = send;
    this.flushIntervalMs = options.flushIntervalMs;
    this.maxBatchSize = options.maxBatchSize;
    this.maxBufferSize = options.maxBufferSize;
    this.retries = options.retries;
    this.logger = options.logger;
    this.onDrop = options.onDrop;
    this.onError = options.onError;
    this.sleep = options.sleep ?? DEFAULT_SLEEP;
    this.setIntervalFn = options.setInterval ?? setInterval;
    this.clearIntervalFn = options.clearInterval ?? clearInterval;
  }

  /** Start the periodic flush timer. No-op if flushIntervalMs <= 0. */
  start(): void {
    if (this.timer || this.flushIntervalMs <= 0) return;
    this.timer = this.setIntervalFn(() => {
      void this.flush();
    }, this.flushIntervalMs);
  }

  /** Enqueue a usage event. Synchronous, non-blocking. */
  add(event: UsageEvent): void {
    if (this.stopped) return;
    if (!this.buffer.has(event.requestId) && this.buffer.size >= this.maxBufferSize) {
      const oldestId = this.orderedIds.shift();
      if (oldestId !== undefined) {
        const dropped = this.buffer.get(oldestId);
        this.buffer.delete(oldestId);
        if (dropped) this.onDrop?.([dropped], 'buffer_full');
      }
    }
    if (!this.buffer.has(event.requestId)) this.orderedIds.push(event.requestId);
    this.buffer.set(event.requestId, event);
    if (this.buffer.size >= this.maxBatchSize) void this.flush();
  }

  /** Flush all buffered events now. Re-entrant: concurrent callers share one flush. */
  flush(): Promise<void> {
    if (this.flushInFlight) return this.flushInFlight;
    this.flushInFlight = this.doFlush().finally(() => {
      this.flushInFlight = null;
    });
    return this.flushInFlight;
  }

  /** Stop accepting events, clear the timer, and await a final flush. */
  async shutdown(): Promise<void> {
    this.stopped = true;
    if (this.timer) {
      this.clearIntervalFn(this.timer);
      this.timer = null;
    }
    await this.flush();
  }

  get size(): number {
    return this.buffer.size;
  }

  private async doFlush(): Promise<void> {
    if (this.buffer.size === 0) return;
    const batch = [...this.buffer.values()];
    for (const e of batch) {
      this.buffer.delete(e.requestId);
      const idx = this.orderedIds.indexOf(e.requestId);
      if (idx >= 0) this.orderedIds.splice(idx, 1);
    }

    let lastErr: unknown = null;
    for (let attempt = 0; attempt <= this.retries; attempt++) {
      try {
        await this.send(batch.map(toDto));
        this.logger?.debug?.('usage flush succeeded', { count: batch.length });
        return;
      } catch (err) {
        lastErr = err;
        const ae = ensureError(err);
        if (attempt < this.retries && isRetriable(ae)) {
          this.logger?.warn?.('usage flush retrying', { attempt: attempt + 1, code: ae.code });
          await this.sleep(backoffMs(attempt));
          continue;
        }
        break;
      }
    }

    const ae = ensureError(lastErr);
    this.onDrop?.(batch, 'max_retries');
    this.onError?.(ae, { events: batch });
    this.logger?.error?.('usage flush failed permanently', { count: batch.length, code: ae.code });
  }
}
